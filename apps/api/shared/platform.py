"""把 `shared/` 的各項能力接成一個可運作的 FastAPI app。

`shared/` 的元件各自有前提: `session_scope()` 要有人在每個請求開 session、`NoChangeError`
要有人轉成 204、`LangException` 要有人先設好這次請求的語系、權限檢查要在 `app.state`
找得到身分來源與權限目錄。這些接線與任何業務無關, 卻是 shared「能正常使用」的條件,
所以跟著 shared 走 —— 整包複製到新專案時, 組裝層只需要呼叫 `create_platform_app()`,
不必照抄一份接線 (漏抄的部分多半不會報錯, 只會在執行期行為不對)。

組裝層仍然決定: 環境設定、權限 enum、啟用哪些 module、app 的名稱與版號。
"""

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
from typing import Protocol

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import text

from shared.auth.catalog import build_permission_catalog
from shared.auth.contracts import AppEnvProtocol, CurrentUser
from shared.auth.dependency import check_user_permission
from shared.auth.permissions import BasePermission
from shared.db.session import configure_session_factory, create_engine, session_scope
from shared.db.table import seed_tables
from shared.http.context import current_request_id, resolve_request_id
from shared.http.errors import NoChangeError, current_language, resolve_language
from shared.module import ModuleManifest, resolve_current_user_resolver, table_models

#: 所有 module 的 router 都掛在這個前綴底下。前端 `shared/api/request.server.ts` 組網址時
#: 會在路徑前補上同一段, 改這裡要一起改那裡。
API_PREFIX = "/api"

# **只放探活路徑**: 長出第二種用途就會變成「某些請求悄悄不留紀錄」的後門。
UNLOGGED_PATHS = frozenset({"/health"})

# 要與 nginx 的 proxy 標頭片段、前端 `shared/api/headers.ts` 一致。
REQUEST_ID_HEADER = "X-Request-ID"


class PlatformEnv(AppEnvProtocol, Protocol):
    """`create_platform_app()` 用得到的環境設定 (`shared/auth` 的那份再加上資料庫)。"""

    postgres_url: str


class _TimingFormatter(logging.Formatter):
    """跟 uvicorn 預設 log 一樣的 `LEVEL:` 對齊寫法, 時間改用 [] 包住。"""

    def formatMessage(self, record: logging.LogRecord) -> str:  # noqa: N802
        separator = " " * (8 - len(record.levelname))
        levelprefix = f"{record.levelname}:{separator}"
        timestamp = self.formatTime(record, self.datefmt)
        return f"{levelprefix}[{timestamp}] {record.message}"


request_logger = logging.getLogger("api.timing")
request_logger.setLevel(logging.INFO)
if not request_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(_TimingFormatter(datefmt="%Y-%m-%d %H:%M:%S"))
    request_logger.addHandler(_handler)
    request_logger.propagate = False


@asynccontextmanager
async def _lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.db_engine = create_engine(application.state.env.postgres_url)
    configure_session_factory(application.state.db_engine)

    async with session_scope() as session:
        await seed_tables(application.state.table_models, session)

    # 刻意只做 seed, **不建表也不做資料回填** —— 那些屬於 migration (compose 的 migrate
    # service 在 api 啟動前跑)。放在這裡的話多個副本會同時搶著改 schema。

    yield

    await application.state.db_engine.dispose()


async def _call_within_session(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """在一個資料庫 session 裡處理這次請求 (見 shared/db/session.py)。

    **要包住 `call_next`**: response_model 驗證與相依項也會讀資料庫。

    **回應是錯誤就一律回滾。** 這一層在 ExceptionMiddleware 外面, service 丟的 4xx 到這裡
    已經是正常的 response, 不會觸發 rollback。少了它, 「先寫入再丟 4xx」的路徑會把寫入
    commit 進去; 撞唯一約束時則會變成 `PendingRollbackError` 的 500 而不是 409
    (`tests/shared/test_platform.py` 守)。
    """
    async with session_scope() as session:
        response = await call_next(request)
        if response.status_code >= 400:
            await session.rollback()
        return response


def _log_request(request: Request, request_id: str, status_code: int, started: float) -> None:
    if request.url.path in UNLOGGED_PATHS:
        return
    duration_ms = (time.perf_counter() - started) * 1000
    client = f"{request.client.host}:{request.client.port}" if request.client else "-"
    # **不要**加上 query string: 那會把敏感內容長期留存在 log 裡。
    http_version = request.scope.get("http_version", "1.1")
    request_logger.info(
        f"[{request_id}] "
        f'{client} - "{request.method} {request.url.path} HTTP/{http_version}"'
        f" {status_code} ({duration_ms:.1f}ms)"
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

    started = time.perf_counter()
    status_code = 500
    try:
        response = await _call_within_session(request, call_next)
        status_code = response.status_code
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
    finally:
        _log_request(request, request_id, status_code, started)


async def _no_change_handler(_request: Request, _exc: NoChangeError) -> Response:
    return Response(status_code=204)


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


def create_platform_app(
    *,
    env: PlatformEnv,
    modules: Iterable[ModuleManifest],
    permissions: type[BasePermission],
    title: str,
    app_version: str,
    contract_version: str,
) -> FastAPI:
    """組出一個掛好平台接線與指定 modules 的 app。

    `permissions` 是專案的權限 enum。權限目錄依**實際傳入的** modules 建立,
    所以用子集合組出來的 app (測試、停用某個 module) 只看得到那些 module 的權限。

    `app_version` 是 `GET /api/system/version` 回報的產品版號, `contract_version` 是
    OpenAPI 的 `info.version`; 兩者刻意分開, 發版才不會讓契約檔跟著變。
    """
    table_list = table_models(modules)
    resolved = tuple(modules)
    catalog = build_permission_catalog(
        permissions, (spec for module in resolved for spec in module.permissions)
    )

    application = FastAPI(title=title, version=contract_version, lifespan=_lifespan)

    application.state.env = env
    application.state.modules = resolved
    application.state.table_models = table_list
    application.state.permission_catalog = catalog
    application.state.permission_resolver = catalog.resolver
    application.state.current_user_resolver = resolve_current_user_resolver(resolved)

    application.middleware("http")(_handle_request)
    application.add_exception_handler(NoChangeError, _no_change_handler)  # type: ignore[arg-type]
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
