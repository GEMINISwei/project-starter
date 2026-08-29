"""每次請求的資料庫 session 邊界（`app/server.py` 的 middleware）。

**為什麼值得單獨測**：這一層在 Starlette 的 ExceptionMiddleware **外面**，所以 service
丟出的 `LangException` 到這裡已經是一個正常回傳的 4xx response —— 沒有例外可以觸發
rollback。少了「錯誤回應一律回滾」那幾行，症狀有兩種，而且都不會有人在 code review 時
看出來：業務規則擋下的請求把半套資料 commit 進去；撞唯一約束的請求則因為 session 已經
進入 pending-rollback 而在 commit 時炸成 500，把本來該回的 409 蓋掉。

不需要真的 PostgreSQL：要驗的是「什麼時候呼叫 commit、什麼時候呼叫 rollback」，
用假的 session factory 替換即可。
"""

import pytest
import pytest_asyncio
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient

from shared.http.errors import BaseError, LangException, LangText
from shared.module import ModuleManifest


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
    """換掉全域 session factory，回傳收集到的 commit/rollback 呼叫順序。"""
    import shared.db.session as session_module

    recorded: list[str] = []
    monkeypatch.setattr(session_module, "_session_factory", lambda: _FakeSession(recorded))
    return recorded


@pytest_asyncio.fixture
async def probe_client():
    """一個只有三條路由的最小 app：成功、業務錯誤、未攔截例外。

    刻意不用正式的 app —— 這裡要驗的是 middleware 的交易邊界，不該綁在任何模組的
    權限或 schema 上（那些改了不應該讓這批測試壞掉）。
    """
    from app.server import create_app

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

    application = create_app((ModuleManifest("probe", routers=(router,)),))
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
    """4xx 要回滾，而且**不可以**把狀態碼換掉。

    `commit` 仍會被呼叫（`session_scope` 離開時），但那時 session 已經乾淨，
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
    """未攔截的例外走 `session_scope` 自己的 except 分支，完全不該 commit。"""
    response = await probe_client.get("/api/probe/boom")

    assert response.status_code == 500
    assert calls == ["rollback"]
