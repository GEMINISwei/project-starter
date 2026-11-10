"""把 `shared/` 的各項能力接成一個可運作的 FastAPI app。

`shared/` 的元件各自有前提: `session_scope()` 要有人在每個請求開 session、`NoChangeError`
要有人轉成 204、`LangException` 要有人先設好這次請求的語系、權限檢查要在 `app.state`
找得到身分來源與權限目錄。這些接線與任何業務無關, 卻是 shared「能正常使用」的條件,
所以跟著 shared 走: 組裝層只需要呼叫 `create_platform_app()`, 不必自己接一份
(漏接的部分多半不會報錯, 只會在執行期行為不對)。

組裝層仍然決定: 環境設定、權限 enum、啟用哪些 module、app 的名稱與版號。
"""

import logging
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
from typing import Protocol

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.auth.catalog import build_permission_catalog
from shared.auth.contracts import AppEnvProtocol, CurrentUser
from shared.auth.dependency import check_user_permission
from shared.auth.permissions import BasePermission
from shared.db.session import configure_session_factory, create_engine, session_scope
from shared.db.table import foreign_key_error, is_foreign_key_violation
from shared.events import EventBus, use_event_bus
from shared.http.context import (
    current_client_ip,
    current_request_id,
    resolve_request_id,
)
from shared.http.errors import (
    BaseError,
    LangException,
    LangText,
    NoChangeError,
    current_language,
    resolve_language,
)
from shared.http.rate_limit import client_ip
from shared.logs import stream_logger
from shared.module import (
    ModuleManifest,
    event_handlers,
    resolve_current_user_resolver,
    table_models,
)

#: 所有 module 的 router 都掛在這個前綴底下。前端 `shared/api/request.server.ts` 組網址時
#: 會在路徑前補上同一段, 改這裡要一起改那裡。
API_PREFIX = "/api"

# **只放探活路徑**: 長出第二種用途就會變成「某些請求悄悄不留紀錄」的後門。
UNLOGGED_PATHS = frozenset({"/health"})

# 要與 nginx 的 proxy 標頭片段、前端 `shared/api/headers.ts` 一致。
REQUEST_ID_HEADER = "X-Request-ID"

# 超過這個耗時的請求記成 WARNING, `grep WARNING` 就挑得出效能問題。固定值不開放設定:
# 它只決定紀錄的等級, 不影響任何行為。
SLOW_REQUEST_MS = 1000


class PlatformError(BaseError):
    INTERNAL = LangText(zh="伺服器發生錯誤", en="Internal Server Error")


class PlatformEnv(AppEnvProtocol, Protocol):
    """`create_platform_app()` 用得到的環境設定 (`shared/auth` 的那份再加上資料庫與執行模式)。"""

    postgres_url: str

    # 唯讀屬性: 專案的設定是 Literal, 可寫的 Protocol 成員會因為不變性而對不上。
    @property
    def mode(self) -> str: ...


request_logger = stream_logger("api.timing")


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.db_engine = create_engine(application.state.env.postgres_url)
    configure_session_factory(application.state.db_engine)

    # 對照「從哪一版開始壞」時, 要看得出那個時間點跑的是哪一版。
    modules = ",".join(module.name for module in application.state.modules) or "-"
    request_logger.info(
        f"啟動 {application.title} v{application.state.app_version}"
        f" mode={application.state.env.mode} modules={modules}"
    )

    # 開機時刻意**不寫任何資料**: 建表、資料回填與初始資料 (seed) 都屬於 compose 的 migrate
    # 服務 (`scripts/db.py migrate`), 它在 api 啟動前跑, 而 `make start` 先單獨跑它、失敗就
    # 不切換服務。寫在這裡的話, 失敗發生在舊容器已經被換掉之後, 整個站就停了。

    yield

    await application.state.db_engine.dispose()


async def _call_within_session(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """在一個資料庫 session 裡處理這次請求 (見 shared/db/session.py), 事件訂閱表也在這裡設定。

    **要包住 `call_next`**: response_model 驗證與相依項也會讀資料庫。

    **回應是錯誤就一律回滾。** 這一層在 ExceptionMiddleware 外面, service 丟的 4xx 到這裡
    已經是正常的 response, 不會觸發 rollback。少了它, 「先寫入再丟 4xx」的路徑會把寫入
    commit 進去; 撞唯一約束時則會變成 `PendingRollbackError` 的 500 而不是 409
    (`tests/shared/test_platform.py` 守)。
    """
    with use_event_bus(request.app.state.event_bus):
        async with session_scope() as session:
            response = await call_next(request)
            if response.status_code >= 400:
                await session.rollback()
            return response


# IPv4 與 IPv6 會用到的字元。值來自標頭: 繞過 nginx 直接打 api 時由對方說了算 (compose 內網做得到),
# 不檢查的話可以塞進假的欄位或一整行假的紀錄。
_LOGGABLE_IP = re.compile(r"^[0-9A-Fa-f:.]{1,45}$")


def _loggable_ip(request: Request) -> str:
    ip = client_ip(request)
    return ip if _LOGGABLE_IP.match(ip) else "invalid"


def _log_request(request: Request, request_id: str, status_code: int, started: float) -> None:
    if request.url.path in UNLOGGED_PATHS:
        return
    duration_ms = (time.perf_counter() - started) * 1000
    # 權限檢查的 dependency 寫進 `request.state`: 路由跑在另一個 task,
    # 它設的 ContextVar 這裡讀不到。
    user_id = getattr(request.state, "user_id", "-")
    client = f"user_id={user_id} {current_client_ip.get()}"
    # **不要**加上 query string: 那會把敏感內容長期留存在 log 裡。
    http_version = request.scope.get("http_version", "1.1")
    level = logging.WARNING if duration_ms > SLOW_REQUEST_MS else logging.INFO
    request_logger.log(
        level,
        f"[{request_id}] "
        f'{client} - "{request.method} {request.url.path} HTTP/{http_version}"'
        f" {status_code} ({duration_ms:.1f}ms)",
    )


async def _handle_request(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """每個請求的共同前置: 語系、request id、資料庫 session 與請求紀錄。"""
    current_language.set(resolve_language(request.headers.get("accept-language")))

    # 沿用上游的追蹤識別碼, 三個行程的 log 才串得起來。
    request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
    current_request_id.set(request_id)
    # 在 `call_next` 之前設: 路由的 task 會複製這時的 context, AUDIT 才讀得到。
    current_client_ip.set(_loggable_ip(request))

    started = time.perf_counter()
    status_code = 500
    try:
        try:
            response = await _call_within_session(request, call_next)
        except Exception:
            # 自己攔下來印: 交給 uvicorn 的話 traceback 不帶 request id, 同時有好幾個 500 時
            # 分不出哪段屬於哪個請求。資料庫 session 在 `_call_within_session` 裡已經回滾。
            request_logger.exception(
                f"[{request_id}] 未處理的例外 {request.method} {request.url.path}"
            )
            response = JSONResponse(
                status_code=500,
                content={"detail": LangException(500, PlatformError.INTERNAL).detail},
            )
        status_code = response.status_code
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
    finally:
        _log_request(request, request_id, status_code, started)


async def _no_change_handler(_request: Request, _exc: NoChangeError) -> Response:
    return Response(status_code=204)


async def _integrity_handler(request: Request, exc: Exception) -> Response:
    """外鍵違反統一轉成 409, 模組只要在資料庫宣告 `RESTRICT`, 不必各自攔。

    其他完整性錯誤 (唯一約束等) 原樣拋出: 那要由模組依業務判斷 (例: users 的帳號重複),
    平台猜不出該回什麼。回應交給 FastAPI 處理 `LangException` 的那一份, 形狀才與其他錯誤一致。
    """
    # 參數型別寫 `Exception` 而不是 `IntegrityError`: 那才是 Starlette 宣告的 handler 型別,
    # 不必在掛載處加 type: ignore。
    if not isinstance(exc, IntegrityError) or not is_foreign_key_violation(exc):
        raise exc
    return await http_exception_handler(request, LangException(409, foreign_key_error(exc)))


async def _validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # 內容與 FastAPI 內建的相同, 刻意留著當具名掛點: 要做 422 訊息的語系對應表時改這裡。
    # 前端 `shared/api/request.server.ts` 依賴 `detail` 是陣列來標出欄位錯誤。
    return JSONResponse(status_code=422, content=jsonable_encoder({"detail": exc.errors()}))


def _install_health_check(application: FastAPI) -> None:
    @application.get("/health", include_in_schema=False)
    async def health_check() -> dict[str, str]:
        # 真的查一次資料庫: API 沒有資料庫就服務不了任何一條路由。
        async with application.state.db_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return {"status": "ok"}


class AppVersion(BaseModel):
    """系統目前執行的版本。"""

    version: str


def _install_version_route(application: FastAPI, app_version: str) -> None:
    # 前端顯示的版號以後端為準: 只有 `APP_VERSION` 跟著發版, 前端的 package.json 不跟。
    # 要求登入: 未登入就能查到確切版本, 等於替人對照已知漏洞。
    router = APIRouter(prefix="/system", tags=["system"])

    @router.get("/version")
    async def get_app_version_route(
        _: CurrentUser = Depends(check_user_permission()),
    ) -> AppVersion:
        """取得系統目前執行的版本。"""
        return AppVersion(version=app_version)

    application.include_router(router, prefix=API_PREFIX)


@asynccontextmanager
async def platform_scope(
    modules: Iterable[ModuleManifest], postgres_url: str
) -> AsyncIterator[AsyncSession]:
    """非 HTTP 入口 (CLI、背景工作) **唯一**的進入點: 與 HTTP 請求相同的 session 與事件訂閱表。

    每個入口自己設定的話, 平台每多一項「每個入口都要有」的東西就要逐一補上, 漏掉的那個
    要到執行期才出錯。正常結束時 commit, 例外時 rollback (同 `session_scope()`)。
    """
    engine = create_engine(postgres_url)
    configure_session_factory(engine)
    try:
        with use_event_bus(EventBus(event_handlers(modules))):
            async with session_scope() as session:
                yield session
    finally:
        await engine.dispose()


def create_platform_app(
    *,
    env: PlatformEnv,
    modules: Iterable[ModuleManifest],
    permissions: type[BasePermission],
    title: str,
    app_version: str,
) -> FastAPI:
    """組出一個掛好平台接線與指定 modules 的 app。

    `permissions` 是專案的權限 enum。權限目錄依**實際傳入的** modules 建立,
    所以用子集合組出來的 app (測試、停用某個 module) 只看得到那些 module 的權限。

    `app_version` 是 `GET /api/system/version` 回報的產品版號, 刻意不進 OpenAPI 的 `info.version`。
    """
    table_list = table_models(modules)
    resolved = tuple(modules)
    catalog = build_permission_catalog(
        permissions, (spec for module in resolved for spec in module.permissions)
    )

    # `info.version` 是 OpenAPI 規格的必填欄位, 但前後端同一個 repo、一起部署, 沒有人讀它:
    # 契約的變更看 contracts/openapi.json 的 diff。固定不動, 發版才不會讓契約檔跟著變。
    application = FastAPI(title=title, version="1", lifespan=_lifespan)

    application.state.env = env
    application.state.app_version = app_version
    application.state.modules = resolved
    application.state.table_models = table_list
    application.state.permission_catalog = catalog
    application.state.permission_resolver = catalog.resolver
    application.state.current_user_resolver = resolve_current_user_resolver(resolved)
    application.state.event_bus = EventBus(event_handlers(resolved))

    application.middleware("http")(_handle_request)
    application.add_exception_handler(NoChangeError, _no_change_handler)  # type: ignore[arg-type]
    application.add_exception_handler(IntegrityError, _integrity_handler)
    application.add_exception_handler(
        RequestValidationError,
        _validation_handler,  # type: ignore[arg-type]
    )
    _install_health_check(application)
    _install_version_route(application, app_version)

    for module in resolved:
        for router in module.routers:
            application.include_router(router, prefix=API_PREFIX)

    return application
