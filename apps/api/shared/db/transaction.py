"""把一組寫入包成單一資料庫交易。"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.session import _current_session, session_scope


@asynccontextmanager
async def transaction() -> AsyncIterator[AsyncSession]:
    """用法:

        async with transaction() as session:
            await XxxTable.create(data, session=session)
            await YyyTable.update_by_id(id, data=..., session=session)

    所有 `BaseTable` 的 CRUD 方法都接受 `session`, 把它一路傳下去即可。

    保證的是**區塊的原子性**: 區塊內丟出例外時, 區塊內的寫入全部撤銷, 例外原樣往外拋。

    - 已經有當前 session (HTTP 請求裡): 開一個 SAVEPOINT。成功時只釋放 savepoint,
      **不 commit** —— 提交仍由開 session 的那一層決定 (middleware 在回應是錯誤時整批回滾)。
      在這裡 commit 的話, 同一次請求稍後丟出的 4xx 就回滾不了區塊裡 (以及更早) 的寫入,
      而且 session 的交易邊界會變成「上一次有人 commit 的地方」, 沒有人說得清楚。
    - 沒有當前 session (CLI、背景工作): 自己開一段 session, 離開時 commit。
    """
    session = _current_session.get()
    if session is not None:
        async with session.begin_nested():
            yield session
        return

    # 沒有當前 session 就自己開一段。這是刻意與 `active_session()` 不同的地方:
    # `transaction()` 本身就是明確的交易邊界, 自己開一個不會讓任何原子性保證消失;
    # 而裸的 model 呼叫自己開 session 才會。
    async with session_scope() as session:
        yield session
