"""平台接線 (`shared/platform.py`): 請求紀錄、request id、每個請求的資料庫 session 邊界,
以及「只靠 shared 就組得出一個 app」。

用 `minimal_app.py` 的環境設定與權限 enum 組 app, 不 import `app.*` —— 這批測試要能跟著
`shared/` 一起被複製到別的專案 (`tests/test_architecture.py` 與 `make check portable` 守)。
"""

import logging
from collections.abc import Iterator

import pytest
import pytest_asyncio
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from shared.auth.contracts import CurrentUser
from shared.auth.tokens import create_token
from shared.http.errors import BaseError, LangException, LangText
from shared.module import ModuleManifest
from tests.shared.minimal_app import CONTRACT_MODULE, MinimalEnv, create_minimal_app


def test_platform_app_builds_without_any_module():
    """新專案還沒有任何 module 時, shared 本身就要組得出一個能回應的 app。"""
    application = create_minimal_app()

    assert application.state.modules == ()
    assert application.state.table_models == []
    assert application.state.current_user_resolver is None


def test_minimal_contract_exposes_the_platform_schemas():
    """前端 shared 假設後端的 OpenAPI 一定有這兩個 schema (`shared/api/entities.ts`)。"""
    schemas = create_minimal_app(CONTRACT_MODULE).openapi()["components"]["schemas"]

    assert {"Permission", "Language"} <= set(schemas)


def test_platform_app_rejects_two_current_user_resolvers():
    async def resolver(username: str) -> CurrentUser | None:
        return None

    with pytest.raises(RuntimeError, match="multiple modules provide current_user_resolver"):
        create_minimal_app(
            ModuleManifest("one", current_user_resolver=resolver),
            ModuleManifest("two", current_user_resolver=resolver),
        )


# ── 請求紀錄與 request id ─────────────────────────────────────────────────────
#
# 守的是一個兩邊都會安靜失敗的東西: 排除清單漏掉 `/health`, log 就被每 10 秒一次的
# healthcheck 淹掉; 清單長太多, 真實請求會悄悄不留紀錄, 而這份 log 是這個專案唯一的
# 可觀測性 (見 docs/operations.md)。所以正反兩面都要斷言。


class _StubConnection:
    async def execute(self, *_args, **_kwargs) -> None:
        return None

    async def __aenter__(self) -> _StubConnection:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        return None


class _StubEngine:
    """`/health` 只用到 `engine.connect()` 加一句 SELECT, 給它這些就夠。

    ASGITransport 不會跑 lifespan, 所以 `app.state.db_engine` 本來是不存在的。
    """

    def connect(self) -> _StubConnection:
        return _StubConnection()


@pytest.fixture
def records() -> Iterator[list[logging.LogRecord]]:
    """直接掛 handler 收 `api.timing` 的紀錄。

    不能用 pytest 的 `caplog`: 那份 fixture 靠 root logger 收, 而 `api.timing` 是
    `propagate = False` (`shared/platform.py`), 紀錄根本不會往上傳, caplog 會一直是空的 ——
    測試於是永遠通過, 包括在排除清單壞掉的時候。
    """
    collected: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            collected.append(record)

    logger = logging.getLogger("api.timing")
    handler = _Collector()
    logger.addHandler(handler)
    try:
        yield collected
    finally:
        logger.removeHandler(handler)


@pytest_asyncio.fixture
async def client():
    app = create_minimal_app()
    app.state.db_engine = _StubEngine()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_health_check_is_not_logged(client: AsyncClient, records: list[logging.LogRecord]):
    response = await client.get("/health")

    assert response.status_code == 200
    assert records == []


@pytest.mark.asyncio
async def test_other_requests_are_logged(client: AsyncClient, records: list[logging.LogRecord]):
    """排除清單不能誤傷一般請求 —— 連沒對到路由的也要留下紀錄。"""
    await client.get("/definitely-not-a-route")

    assert len(records) == 1
    assert "GET /definitely-not-a-route" in records[0].getMessage()
    assert " 404 " in records[0].getMessage()


@pytest.mark.asyncio
async def test_request_id_is_reused_when_upstream_sends_one(
    client: AsyncClient, records: list[logging.LogRecord]
):
    """沿用上游的 id 才串得起來 —— nginx、Next 與 API 是三段不同的行程。"""
    response = await client.get("/definitely-not-a-route", headers={"X-Request-ID": "abc123"})

    assert response.headers["X-Request-ID"] == "abc123"
    assert "[abc123]" in records[0].getMessage()


@pytest.mark.asyncio
async def test_request_id_is_generated_when_missing(
    client: AsyncClient, records: list[logging.LogRecord]
):
    response = await client.get("/definitely-not-a-route")

    generated = response.headers["X-Request-ID"]
    assert generated and generated != "-"
    assert f"[{generated}]" in records[0].getMessage()


@pytest.mark.asyncio
async def test_unsafe_request_id_is_replaced(
    client: AsyncClient, records: list[logging.LogRecord]
):
    """帶換行的值可以偽造出一整行假的請求紀錄, 所以不合格的一律換掉而不是照抄。"""
    response = await client.get(
        "/definitely-not-a-route", headers={"X-Request-ID": "a b\tc"}
    )

    assert response.headers["X-Request-ID"] != "a b\tc"
    assert "a b" not in records[0].getMessage()

# ── 每次請求的資料庫 session 邊界 ─────────────────────────────────────────────
#
# 這一層在 Starlette 的 ExceptionMiddleware **外面**, 所以 service 丟出的 `LangException`
# 到這裡已經是一個正常回傳的 4xx response —— 沒有例外可以觸發 rollback。少了「錯誤回應
# 一律回滾」那幾行, 症狀有兩種, 而且都不會有人在 code review 時看出來: 業務規則擋下的請求
# 把半套資料 commit 進去; 撞唯一約束的請求則因為 session 已經進入 pending-rollback 而在
# commit 時炸成 500, 把本來該回的 409 蓋掉。
#
# 不需要真的 PostgreSQL: 要驗的是「什麼時候呼叫 commit、什麼時候呼叫 rollback」,
# 用假的 session factory 替換即可。


class _ProbeError(BaseError):
    REJECTED = LangText(zh="被拒絕", en="Rejected")


class _FakeSession:
    def __init__(self, calls: list[str]) -> None:
        self._calls = calls

    async def commit(self) -> None:
        self._calls.append("commit")

    async def rollback(self) -> None:
        self._calls.append("rollback")

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        return None


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """換掉全域 session factory, 回傳收集到的 commit/rollback 呼叫順序。"""
    import shared.db.session as session_module

    recorded: list[str] = []
    monkeypatch.setattr(session_module, "_session_factory", lambda: _FakeSession(recorded))
    return recorded


@pytest_asyncio.fixture
async def probe_client():
    """一個只有三條路由的最小 app: 成功、業務錯誤、未攔截例外。"""
    router = APIRouter(prefix="/probe")

    @router.get("/ok")
    async def ok_route() -> dict[str, bool]:
        return {"ok": True}

    @router.get("/rejected")
    async def rejected_route() -> dict[str, bool]:
        raise LangException(409, _ProbeError.REJECTED)

    @router.get("/boom")
    async def boom_route() -> dict[str, bool]:
        raise RuntimeError("boom")

    application = create_minimal_app(ModuleManifest("probe", routers=(router,)))
    transport = ASGITransport(app=application, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_successful_request_commits(probe_client: AsyncClient, calls: list[str]):
    response = await probe_client.get("/api/probe/ok")

    assert response.status_code == 200
    assert calls == ["commit"]


@pytest.mark.asyncio
async def test_error_response_rolls_back_and_keeps_its_status(
    probe_client: AsyncClient, calls: list[str]
):
    """4xx 要回滾, 而且**不可以**把狀態碼換掉。

    `commit` 仍會被呼叫 (`session_scope` 離開時), 但那時 session 已經乾淨,
    commit 一個空交易是 no-op —— 重點是 rollback 必須排在它前面。
    """
    response = await probe_client.get("/api/probe/rejected")

    assert response.status_code == 409
    assert calls[0] == "rollback"
    assert "commit" not in calls[:1]


@pytest.mark.asyncio
async def test_unhandled_exception_rolls_back_and_never_commits(
    probe_client: AsyncClient, calls: list[str]
):
    """未攔截的例外走 `session_scope` 自己的 except 分支, 完全不該 commit。"""
    response = await probe_client.get("/api/probe/boom")

    assert response.status_code == 500
    assert calls == ["rollback"]


# ── 版號 ─────────────────────────────────────────────────────────────────────
#
# 產品版號與 OpenAPI 的 `info.version` 是兩件事: 前者每次發版都變, 後者只在契約有破壞性變更時
# 手動改。綁在一起的話, 每次發版 contracts/openapi.json 都會出現一筆跟契約無關的 diff。


async def _member_resolver(username: str) -> CurrentUser | None:
    return {
        "id": "member",
        "username": username,
        "auth_version": 1,
        # 只要求「有登入」, 所以刻意不給任何權限。
        "permissions": [],
        "is_disabled": False,
    }


@pytest_asyncio.fixture
async def version_client():
    application = create_minimal_app(
        ModuleManifest("member", current_user_resolver=_member_resolver), app_version="1.2.3"
    )
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_version_route_returns_the_app_version(version_client: AsyncClient, calls: list[str]):
    token = create_token({"username": "member", "auth_version": 1}, MinimalEnv())
    version_client.cookies.set("access_token", token["access_token"])

    response = await version_client.get("/api/system/version")

    assert response.status_code == 200
    assert response.json() == {"version": "1.2.3"}


@pytest.mark.asyncio
async def test_version_route_requires_authentication(
    version_client: AsyncClient, calls: list[str]
):
    response = await version_client.get("/api/system/version")

    assert response.status_code == 401


def test_openapi_version_is_independent_of_app_version():
    openapi = create_minimal_app(app_version="1.2.3", contract_version="7").openapi()

    assert openapi["info"]["version"] == "7"
