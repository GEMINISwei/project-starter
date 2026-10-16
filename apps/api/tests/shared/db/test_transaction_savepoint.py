"""`transaction()` 在請求裡是 SAVEPOINT: 對真的 PostgreSQL 驗證交易邊界。

`test_transaction.py` 用假 session 驗呼叫順序; 這裡驗的是那個順序在資料庫裡的**結果** ——
區塊失敗只撤銷區塊內的寫入, 區塊成功也不會提前 commit, 請求最後回滾時一起消失。
後者是改成 savepoint 的理由: 以前區塊會直接 commit, middleware 的「回應是錯誤就回滾」
對區塊裡的寫入就悄悄失效了。
"""

import pytest
from sqlalchemy import func, select

from shared.db.session import session_scope
from shared.db.transaction import transaction

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _names(model) -> set[str]:
    async with session_scope() as session:
        return set((await session.scalars(select(model.name))).all())


async def test_failed_block_undoes_only_its_own_writes(empty_detail_table):
    model = empty_detail_table

    async with session_scope():
        await model.create({"name": "before"})
        with pytest.raises(RuntimeError):
            async with transaction() as session:
                await model.create({"name": "inside"}, session=session)
                raise RuntimeError("block fails")
        await model.create({"name": "after"})

    assert await _names(model) == {"before", "after"}


async def test_successful_block_is_rolled_back_with_the_request(empty_detail_table):
    """模擬 middleware: 區塊成功之後, 請求仍以錯誤回應收場而整批回滾。"""
    model = empty_detail_table

    async with session_scope() as request_session:
        async with transaction() as session:
            await model.create({"name": "inside"}, session=session)
        await request_session.rollback()

    async with session_scope() as session:
        assert await session.scalar(select(func.count()).select_from(model)) == 0
