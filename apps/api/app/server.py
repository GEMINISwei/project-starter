import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text

from app.config import APP_VERSION, env
from app.permissions import build_permission_catalog
from app.registry import (
    ENABLED_MODULES,
    resolve_current_user_resolver,
    table_models,
    validate_modules,
)
from shared.db.session import configure_session_factory, create_engine, session_scope
from shared.http.context import current_request_id, resolve_request_id
from shared.http.errors import NoChangeError, current_language, resolve_language
from shared.module import ModuleManifest


class _TimingFormatter(logging.Formatter):
    """跟 uvicorn 預設 log 一樣的 `LEVEL:` 對齊寫法，時間改用 [] 包住。"""

    def formatMessage(self, record: logging.LogRecord) -> str:  # noqa: N802
        separator = " " * (8 - len(record.levelname))
        levelprefix = f"{record.levelname}:{separator}"
        timestamp = self.formatTime(record, self.datefmt)
        return f"{levelprefix}[{timestamp}] {record.message}"


# 探活路徑不寫進請求紀錄：healthcheck 每 10 秒打一次，記下來只會把真正的請求淹掉。
#
# 這份清單刻意**只放**探活路徑：一旦長出第二種用途，就會變成「某些請求悄悄不留紀錄」的後門，
# 而這份 log 是這個專案唯一的可觀測性（見 docs/operations.md）。
UNLOGGED_PATHS = frozenset({"/health"})

# 追蹤識別碼的 header 名稱。**三處要一致**：nginx 的兩份模板（以 `$request_id` 覆寫）、前端
# `shared/api/headers.ts`，以及這裡。
REQUEST_ID_HEADER = "X-Request-ID"

request_logger = logging.getLogger("api.timing")
request_logger.setLevel(logging.INFO)
if not request_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(_TimingFormatter(datefmt="%Y-%m-%d %H:%M:%S"))
    request_logger.addHandler(_handler)
    request_logger.propagate = False


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    application.state.db_engine = create_engine(env.postgres_url)
    configure_session_factory(application.state.db_engine)

    async with session_scope() as session:
        for model in application.state.table_models:
            await model.ensure_seed(session=session)

    # 這裡刻意只做 seed，**不建表也不做資料回填**。
    # 建表與結構變更屬於 migration（見 scripts/migrations/ 與 shared/db/migration.py）：
    # 放在啟動流程裡的話，多個 API 副本同時啟動會互相搶著改 schema，而且「新程式碼
    # 服務舊結構」那道保證就消失了。部署流程請在服務啟動前執行
    # `python scripts/db.py migrate`（compose 已經有一個一次性的 migrate service 在做）。

    yield

    await application.state.db_engine.dispose()


async def _call_within_session(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """在一個資料庫 session 裡處理這次請求（見 shared/db/session.py）。

    **要包住 `call_next`**，不能只包路由函式 —— FastAPI 的 response_model 驗證與
    相依項也會讀資料庫。

    **回應是錯誤就一律回滾。** 這一層在 Starlette 的 ExceptionMiddleware **外面**，
    所以 service 丟出的 `LangException` 到這裡已經變成一個正常回傳的 4xx response ——
    沒有例外可以觸發 `session_scope` 的 rollback。少了那兩行有兩個後果：

    1. 「先寫入、再因為業務規則丟 4xx」的路徑會把那筆寫入 commit 進去。
    2. 更糟的是撞唯一約束那條：`IntegrityError` 已經讓交易在資料庫端中止，session 進入
       pending-rollback，接著的 commit 會丟 `PendingRollbackError` —— 使用者看到的是
       500，而不是本來要回的 409。`modules/users/service.py` 的 `create_user`
       正是這條路徑。`tests/test_request_session.py` 在守這件事。

    抽成獨立函式而不是寫在 middleware 裡：那個 middleware 已經同時負責語系、追蹤
    識別碼與請求紀錄，再多一層巢狀就會被 `C901` 擋下來 —— 而那個門檻擋的正是
    「一個函式長到沒人敢動」。
    """
    async with session_scope() as session:
        response = await call_next(request)
        if response.status_code >= 400:
            await session.rollback()
        return response


def create_app(modules: tuple[ModuleManifest, ...] = ENABLED_MODULES) -> FastAPI:
    modules = validate_modules(modules)
    # 權限目錄跟著「這個 app 實際啟用了哪些 module」走，而不是跟著全域清單走 ——
    # 否則 `create_app(不含 items)` 組出來的服務，`GET /permissions/` 仍會提供 items 的權限。
    permission_catalog = build_permission_catalog(
        spec for module in modules for spec in module.permissions
    )

    application = FastAPI(
        title=env.project_name or "API",
        version=APP_VERSION,
        lifespan=lifespan,
    )

    application.state.env = env
    application.state.modules = modules
    application.state.table_models = table_models(modules)
    application.state.permission_catalog = permission_catalog
    application.state.permission_resolver = permission_catalog.resolver
    # 身分來源由 manifest 提供（見 ModuleManifest.current_user_resolver）。
    # 組裝層刻意不 import 任何具名 module —— 它只認得 manifest 這個契約。
    application.state.current_user_resolver = resolve_current_user_resolver(modules)

    for module in modules:
        if module.configure is not None:
            module.configure(env)

    @application.middleware("http")
    async def log_request_timing(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # 設定本次請求的錯誤訊息語言，讓 service 深處丟出的 LangException 自動使用正確語系。
        current_language.set(resolve_language(request.headers.get("accept-language")))

        # 追蹤識別碼：有上游送來就沿用，否則產一個。沿用是重點 —— nginx、Next 伺服器端與
        # 這個 API 是三段不同的行程，同一次使用者操作要靠同一個 id 才在三份 log 裡串得起來。
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        current_request_id.set(request_id)

        start = time.perf_counter()
        status_code = 500
        try:
            response = await _call_within_session(request, call_next)
            status_code = response.status_code
            # 回寫給呼叫端。使用者回報問題時能直接給出這個值，比對 log 就不必靠時間戳猜。
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        finally:
            # 放在 finally，確保未攔截例外也會留下請求紀錄。
            if request.url.path not in UNLOGGED_PATHS:
                duration_ms = (time.perf_counter() - start) * 1000
                client = f"{request.client.host}:{request.client.port}" if request.client else "-"
                # 只記錄 path，**不要**加上 query string：query 會帶到 ws ticket、邀請碼、
                # 搜尋關鍵字等敏感內容，寫進 log 就等於長期留存。
                http_version = request.scope.get("http_version", "1.1")
                request_logger.info(
                    f"[{request_id}] "
                    f'{client} - "{request.method} {request.url.path} HTTP/{http_version}"'
                    f" {status_code} ({duration_ms:.1f}ms)"
                )

    @application.get("/health", include_in_schema=False)
    async def health_check() -> dict[str, str]:
        # 真的往資料庫下一句 SELECT，而不是只看引擎物件存不存在：healthcheck 要回答的是
        # 「這個容器現在服務得了請求嗎」，而 API 沒有資料庫就服務不了任何一條路由。
        async with application.state.db_engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        return {"status": "ok"}

    @application.exception_handler(NoChangeError)
    async def no_change_handler(request: Request, exc: NoChangeError) -> Response:
        return Response(status_code=204)

    # 內容與 FastAPI 內建的 handler 相同，這是刻意的：留著它是為了有一個**具名的**掛點 ——
    # docs/extending.md 的 i18n 章節指名在這裡對 `exc.errors()` 的 `type` 做中文對應表。
    # 看起來像多餘的覆寫而把它刪掉，那份文件就會指向不存在的東西（check-docs.sh 不掃程式碼區塊）。
    @application.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=jsonable_encoder({"detail": exc.errors()}),
        )

    for module in modules:
        for router in module.routers:
            application.include_router(router, prefix="/api")

    return application


app = create_app()
