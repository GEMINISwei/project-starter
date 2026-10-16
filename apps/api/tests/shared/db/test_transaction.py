"""`shared/db/transaction.py` 的交易語義保證。

和 `test_migration.py` 同一類的風險: 這段程式碼包住的是多筆寫入的原子性, 出錯的表現
不是例外而是**資料悄悄變得不一致**。commit 少呼叫一次, 寫入就全部消失; rollback 少呼叫
一次, 失敗的半套資料就會留在資料庫裡; 例外被吞掉, 呼叫端還會以為成功。

不需要 PostgreSQL: 請求裡的 `transaction()` 只用到 session 的 `begin_nested()`, 用假物件
替換即可。 (真的連上資料庫的驗證由 `tests/modules/users/test_bootstrap.py` 底下標了
`integration` 的測試負責。)
"""

from collections.abc import Iterator
from contextlib import asynccontextmanager

import pytest

from shared.db.session import _current_session
from shared.db.transaction import transaction


class _FakeSession:
    """記錄交易相關的呼叫。`begin_nested()` 的語義照 SQLAlchemy: 成功釋放、例外回滾並往外拋。"""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def commit(self) -> None:
        self.calls.append("commit")

    async def rollback(self) -> None:
        self.calls.append("rollback")

    @asynccontextmanager
    async def begin_nested(self):
        self.calls.append("savepoint")
        try:
            yield
        except BaseException:
            self.calls.append("rollback_to_savepoint")
            raise
        self.calls.append("release_savepoint")


@pytest.fixture
def session() -> Iterator[_FakeSession]:
    """把假 session 裝進 ContextVar, 模擬「已經在一次 HTTP 請求裡」的情況。

    測試結束一定要 reset: ContextVar 在 pytest 的同一個 event loop 裡會漏到下一條測試,
    症狀是「單獨跑會過、整批跑會壞」。
    """
    fake = _FakeSession()
    token = _current_session.set(fake)  # type: ignore[arg-type]
    yield fake
    _current_session.reset(token)


@pytest.mark.asyncio
async def test_in_request_block_releases_a_savepoint_without_committing(session):
    """請求裡的區塊成功時只釋放 savepoint, **不 commit**。

    提早 commit 的話, 同一次請求稍後丟出的 4xx 就回滾不了區塊裡的寫入: middleware 的
    「回應是錯誤就回滾」會悄悄失效, 而且只在先 transaction() 再出錯的路徑上。
    """
    async with transaction():
        pass

    assert session.calls == ["savepoint", "release_savepoint"]


@pytest.mark.asyncio
async def test_rolls_back_the_savepoint_and_reraises_when_block_raises(session):
    """失敗時只撤銷區塊內的寫入, 而且例外必須原樣往外傳。

    吞掉例外是這裡最危險的寫法: 呼叫端會以為寫入成功, 但資料其實已經被回滾。
    """
    with pytest.raises(ValueError, match="boom"):
        async with transaction():
            raise ValueError("boom")

    assert session.calls == ["savepoint", "rollback_to_savepoint"]


@pytest.mark.asyncio
async def test_never_commits_the_request_session(session):
    """不論成敗, 請求的 session 都由開它的那一層提交 (middleware), 不是這裡。"""
    async with transaction():
        pass
    with pytest.raises(RuntimeError):
        async with transaction():
            raise RuntimeError("failure inside block")

    assert "commit" not in session.calls
    assert "rollback" not in session.calls


@pytest.mark.asyncio
async def test_propagates_original_exception_type_and_message(session):
    """rollback 過程不應該把原始例外換成別的型別, 否則呼叫端無法分辨失敗原因。"""

    class DomainError(Exception):
        pass

    with pytest.raises(DomainError) as exc_info:
        async with transaction():
            raise DomainError("角色不存在")

    assert str(exc_info.value) == "角色不存在"


@pytest.mark.asyncio
async def test_reuses_the_request_session_instead_of_opening_another():
    """在 HTTP 請求裡呼叫時要沿用 middleware 開的那個 session。

    另開一個的後果不是報錯, 而是**兩個交易**: `transaction()` 區塊裡的寫入與同一次
    請求的其他寫入落在不同交易, 回滾時只回一半。
    """
    fake = _FakeSession()
    token = _current_session.set(fake)  # type: ignore[arg-type]
    try:
        async with transaction() as active:
            assert active is fake
    finally:
        _current_session.reset(token)


@pytest.mark.asyncio
async def test_requires_a_session_factory_when_there_is_no_active_session():
    """沒有當前 session 時會自己開一段 (CLI/背景工作的用法)。

    這裡只驗「它真的去要 factory 了」—— factory 沒安裝就是 RuntimeError,
    而不是靜靜地什麼都不做。
    """
    import shared.db.session as session_module

    original = session_module._session_factory
    session_module._session_factory = None
    try:
        with pytest.raises(RuntimeError, match="session factory"):
            async with transaction():
                pass
    finally:
        session_module._session_factory = original
