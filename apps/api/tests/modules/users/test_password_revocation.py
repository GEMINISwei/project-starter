"""撤銷 session 的方法對真的資料庫做了什麼: `set_password_and_revoke_sessions()`
(換密碼) 與 `revoke_sessions()` (登出) 共用同一段 SQL, `revoke_all_sessions()`
(全員登出, `make db revoke-sessions`) 是同一個 `+1` 套在整張表上。

這是「把既有 session 踢下線」的唯一實作, 而它守的兩件事**都只有真的
PostgreSQL 證明得了**:

- `auth_version + 1` 是在 **SQL 裡**算的, 所以兩個併發的換密碼不會互相把版本號寫回舊值。
  用假物件替代的話, 測到的是那個假物件的回傳值。
- `RETURNING` 交出來的是**寫入後**的那個版本號。改自己密碼那條路徑拿它補簽新 token
  (見 `account.change_own_password`), 值錯了的症狀是「改完密碼, 下一個動作就被登出」。

路由層的測試 (`test_routes.py`) 把這個方法換成假物件, 因為那裡要驗的是 HTTP 的形狀。
兩邊合起來才完整: 那裡證明接線對了, 這裡證明底下的 SQL 對了。
"""

import asyncio
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from modules.users.model import UserTable
from shared.db.session import configure_session_factory, create_engine, session_scope
from tests.integration import require_postgres, restore_session_factory


@pytest_asyncio.fixture
async def user_db():
    """一個帶 `users` 表的真資料庫, 裡面有一位 auth_version=1 的使用者, 回傳它的 id。

    **fixture 不進入 session scope**: 底下併發那條測試需要每次呼叫各有自己的交易,
    共用一個的話就退化成同一個交易裡的兩次 UPDATE。
    """
    from shared.db.table import BaseTable

    url = os.environ["POSTGRES_URL"]
    engine = create_engine(url)
    await require_postgres(engine, url)

    with restore_session_factory():
        async with engine.begin() as connection:
            await connection.run_sync(BaseTable.metadata.create_all)
            await connection.execute(delete(UserTable))

        configure_session_factory(engine)

        async with session_scope() as session:
            user = UserTable(username="rotator", password="old-hash", nickname="Rotator")
            session.add(user)
            await session.flush()
            user_id = str(user.id)

        yield user_id

        async with engine.begin() as connection:
            await connection.execute(delete(UserTable))
        await engine.dispose()


async def _auth_version(user_id: str) -> int | None:
    """直接從資料庫讀, 不經過被測方法的回傳值 —— 否則就是拿它自己證明它自己。"""
    async with session_scope() as session:
        return await session.scalar(
            select(UserTable.auth_version).where(UserTable.id == uuid.UUID(user_id))
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_returns_the_auth_version_that_was_written(user_db):
    """回傳值要等於資料庫裡的新版本號, 而且真的往上加了一版。"""
    async with session_scope():
        updated = await UserTable.set_password_and_revoke_sessions(
            id=user_db, password_hash="new-hash"
        )

    assert updated is not None
    assert updated["id"] == user_db
    assert updated["auth_version"] == 2
    assert await _auth_version(user_db) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_password_is_actually_replaced(user_db):
    async with session_scope():
        await UserTable.set_password_and_revoke_sessions(id=user_db, password_hash="new-hash")

    async with session_scope() as session:
        password = await session.scalar(
            select(UserTable.password).where(UserTable.id == uuid.UUID(user_db))
        )

    assert password == "new-hash"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_changes_do_not_lose_a_version(user_db):
    """兩次併發的換密碼要各自推進一版, 最後是 3 而不是 2。

    這條是 `auth_version + 1` 寫在 SQL 裡而不是 Python 裡的理由: 先讀出來再加一,
    兩個交易會讀到同一個舊值、寫回同一個新值 —— 其中一次撤銷就這樣消失了,
    而受害者手上那張「應該已經失效」的 token 仍然通得過。
    """

    async def rotate(password_hash: str):
        async with session_scope():
            return await UserTable.set_password_and_revoke_sessions(
                id=user_db, password_hash=password_hash
            )

    results = await asyncio.gather(rotate("hash-a"), rotate("hash-b"))

    assert {result["auth_version"] for result in results if result} == {2, 3}
    assert await _auth_version(user_db) == 3


@pytest.mark.integration
@pytest.mark.asyncio
async def test_unknown_id_returns_none(user_db):
    """查無此人要回 None (讓呼叫端的 `ensure_found` 轉成 404), 不是丟例外。"""
    async with session_scope():
        assert (
            await UserTable.set_password_and_revoke_sessions(
                id="00000000-0000-0000-0000-000000000000",
                password_hash="new-hash",
            )
            is None
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_malformed_id_returns_none(user_db):
    """格式不合法的 id 同樣是 None —— 對外的 id 是不透明字串, 解析失敗屬於「查不到」。"""
    async with session_scope():
        assert (
            await UserTable.set_password_and_revoke_sessions(id="not-a-uuid", password_hash="x")
            is None
        )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_revoke_sessions_bumps_only_that_user(user_db):
    """登出只撤銷自己: 世代號存在每個帳號自己的那一列上, 別人的 token 不受影響。"""
    async with session_scope() as session:
        other = UserTable(username="bystander", password="hash", nickname="Bystander")
        session.add(other)
        await session.flush()
        other_id = str(other.id)

    async with session_scope():
        updated = await UserTable.revoke_sessions(id=user_db)

    assert updated == {"id": user_db, "auth_version": 2}
    assert await _auth_version(user_db) == 2
    assert await _auth_version(other_id) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_revoke_sessions_keeps_the_password(user_db):
    async with session_scope():
        await UserTable.revoke_sessions(id=user_db)

    async with session_scope() as session:
        password = await session.scalar(
            select(UserTable.password).where(UserTable.id == uuid.UUID(user_db))
        )

    assert password == "old-hash"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_revoke_all_sessions_bumps_every_user(user_db):
    """每個人以**自己目前的**世代 +1: 在 SQL 裡算, 不是寫入同一個常數。"""
    async with session_scope() as session:
        other = UserTable(username="veteran", password="hash", nickname="Veteran", auth_version=5)
        session.add(other)
        await session.flush()
        other_id = str(other.id)

    async with session_scope():
        await UserTable.revoke_all_sessions()

    assert await _auth_version(user_db) == 2
    assert await _auth_version(other_id) == 6


@pytest.mark.integration
@pytest.mark.asyncio
async def test_revoke_all_sessions_returns_affected_count(user_db):
    async with session_scope() as session:
        session.add(UserTable(username="second", password="hash", nickname="Second"))

    async with session_scope():
        affected = await UserTable.revoke_all_sessions()

    assert affected == 2
