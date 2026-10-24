"""`release_connection()`: 請求中途把只讀過的交易結束、連線還回連線池。

要真的 PostgreSQL: 「有沒有寫過」是問資料庫這個交易拿到 transaction id 了沒有,
「連線有沒有還回去」看的是引擎的連線池。
"""

import pytest
from sqlalchemy import Engine, QueuePool, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.session import active_session, release_connection, session_scope

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def checked_out_connections(session: AsyncSession) -> int:
    """這個 session 的引擎目前借出幾條連線。"""
    bind = session.sync_session.get_bind()
    assert isinstance(bind, Engine)
    assert isinstance(bind.pool, QueuePool)
    return bind.pool.checkedout()


async def test_release_connection_ends_read_transaction(empty_detail_table):
    model = empty_detail_table

    async with session_scope() as session:
        await session.scalar(select(func.count()).select_from(model))
        assert session.in_transaction()

        await release_connection()

        assert not session.in_transaction()
        assert checked_out_connections(session) == 0
        # 歸還之後同一個 session 照樣能查, 下一次查詢會自動再拿一條連線。
        assert await active_session().scalar(select(func.count()).select_from(model)) == 0


async def test_release_connection_refuses_after_write(empty_detail_table):
    model = empty_detail_table

    async with session_scope() as session:
        await model.create({"name": "written"})

        with pytest.raises(RuntimeError):
            await release_connection()

        # 拒絕之後交易還在, 寫入沒有被悄悄提交或撤銷。
        assert session.in_transaction()
        assert await session.scalar(select(func.count()).select_from(model)) == 1
        await session.rollback()
