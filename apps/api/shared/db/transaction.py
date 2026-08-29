"""把一組寫入包成單一資料庫交易。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.session import _current_session, session_scope


@asynccontextmanager
async def transaction() -> AsyncIterator[AsyncSession]:
    """用法：

        async with transaction() as session:
            await XxxTable.create(data, session=session)
            await YyyTable.update_by_id(id, data=..., session=session)

    所有 `BaseTable` 的 CRUD 方法都接受 `session`，把它一路傳下去即可。

    離開區塊時 commit，區塊內丟出例外時 rollback 並把例外往外拋。

    連線不必由呼叫端傳進來，它由 `shared/db/session.py` 的 ContextVar 提供。

    在 HTTP 請求裡呼叫時用的是 middleware 已經開好的那個 session（見 session.py），
    所以這個區塊的 commit 也會把同一次請求中**更早**的寫入一起提交。實務上不影響
    正確性（更早的寫入本來就已經成功），但要知道邊界在哪：交易的起點是「上一次
    commit」，不是 `async with` 那一行。
    """
    if _current_session.get() is not None:
        session = _current_session.get()
        assert session is not None  # noqa: S101 —— 上一行剛檢查過，這行只是給 mypy 收窄型別
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        return

    # 沒有當前 session（CLI、背景工作）就自己開一段。這是刻意與 `active_session()`
    # 不同的地方：`transaction()` 本身就是明確的交易邊界，自己開一個不會讓任何
    # 原子性保證消失；而裸的 model 呼叫自己開 session 才會。
    async with session_scope() as session:
        yield session
