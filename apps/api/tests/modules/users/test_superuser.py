"""建立超級管理者 (見 `modules/users/superuser.py`)。

唯一入口是 CLI `scripts/db.py create-superuser`。

測試分成兩部分:
- 不需要資料庫的: 網頁上沒有任何建立超管的入口
- 標 `integration` 的: 建立出來的帳號真的掛上超管角色、可以建第二個、帳號重複時拒絕
"""

import os

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from modules.users import superuser
from modules.users.errors import UserError
from shared.db.session import configure_session_factory, create_engine, session_scope
from shared.http.errors import LangException
from tests.integration import require_postgres, restore_session_factory

# --- 不需要資料庫 ---------------------------------------------------------


def _openapi_operations() -> dict[str, list[str]]:
    """app 對外的每條路徑與它的 operationId。

    不走 `app.routes`: include 進來的 router 在那裡是一個不透明的包裝 (`_IncludedRouter`),
    模組的路由一條都列不出來, 拿它做「不在裡面」的檢查會永遠通過。
    """
    from app.server import app

    return {
        path: [operation.get("operationId", "") for operation in methods.values()]
        for path, methods in app.openapi()["paths"].items()
    }


def test_operation_listing_sees_module_routes():
    """底下兩條都是「不在裡面」的檢查, 列舉方式一旦看不到模組路由就會變成空頭支票。"""
    assert "/api/users/login" in _openapi_operations()


def test_create_super_admin_is_not_exposed_over_http():
    """這條路徑繞過 `validate_role_ids`, 授權模型是「呼叫者握有伺服器 shell」。

    一旦有人把它接上 router, 授權模型就悄悄換成了「某個 permission」——
    那是完全不同的一件事, 而且從 diff 上看起來只是「多了一個端點」。
    """
    for operation_ids in _openapi_operations().values():
        assert not any("create_super_admin" in operation_id for operation_id in operation_ids)


def test_signup_routes_are_not_registered():
    """以註冊代碼建立第一個超管的網頁路徑已經移除, 不能被重新接回來。

    比對路徑而不是打一次請求: `GET /users/bootstrap-status` 會落進 `/users/{user_id}`
    而回 401, 看起來像「有擋住」, 其實什麼都沒驗證到。
    """
    paths = _openapi_operations()

    assert "/api/users/signup" not in paths
    assert "/api/users/bootstrap-status" not in paths


# --- 需要真的資料庫 (PostgreSQL) -------------------------------------------


@pytest_asyncio.fixture
async def superuser_db():
    """連上真的 PostgreSQL 並建好會用到的表, 回傳超級管理者角色的 id。

    要驗證的是帳號真的掛上角色 (關聯表與外鍵) 與 username 的唯一約束,
    那是資料庫提供的保證, mock 掉就什麼都沒測到。
    """
    from modules.roles.model import RoleTable
    from modules.users.model import UserTable, user_roles

    url = os.environ["POSTGRES_URL"]
    engine = create_engine(url)
    await require_postgres(engine, url, "PostgreSQL")

    from shared.db.table import BaseTable

    async def clear(connection):
        await connection.execute(user_roles.delete())
        await connection.execute(delete(UserTable))
        await connection.execute(delete(RoleTable))

    with restore_session_factory():
        async with engine.begin() as connection:
            # 測試資料庫從 model 的 metadata 直接建, 不跑 migration。**這不是第二條
            # 建表路徑**: `make check integration` (CI 也跑) 用 `alembic check`
            # 保證 metadata 與 migration 產生的結構一致, 所以兩者等價, 而這條快得多。
            # 同樣的分工在 Rails 是 `db:schema:load` 對 `db:migrate`。
            await connection.run_sync(BaseTable.metadata.create_all)
            await clear(connection)

        configure_session_factory(engine)

        # 建立超管會去取 seed 出來的系統角色, 這裡直接建一個真的 (外鍵要求它存在)。
        async with session_scope() as session:
            role = RoleTable(code="super_admin", name="超級管理者", permissions=["*"])
            session.add(role)
            await session.flush()
            role_id = str(role.id)

        yield role_id

        async with engine.begin() as connection:
            await clear(connection)
        await engine.dispose()


@pytest.fixture(autouse=True)
def _fixed_super_admin_role(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    """讓 `get_super_admin_role_id()` 回傳 fixture 建好的那個角色。

    不 mock 的話它會走 `ensure_seed()`, 而那會把角色的 seed 資料寫進測試資料庫 ——
    測到的就變成 seed 的行為, 不是建立超管的行為。
    """
    if "superuser_db" not in request.fixturenames:
        return

    from modules.roles.model import RoleTable

    async def role_id():
        return request.getfixturevalue("superuser_db")

    monkeypatch.setattr(RoleTable, "get_super_admin_role_id", role_id)


async def count(model) -> int:
    """目前表裡有幾列。開自己的 session, 不依賴呼叫端的交易狀態。"""
    async with session_scope() as session:
        return await session.scalar(select(func.count()).select_from(model)) or 0


async def in_session(coroutine_factory):
    """在一個獨立的 session (= 一個獨立的交易) 裡跑一段程式。"""
    async with session_scope():
        return await coroutine_factory()


def _super_admin_form(username: str = "root"):
    from modules.users.schema import SuperAdminCreate

    return SuperAdminCreate(
        username=username,
        password="sup3r-secret",
        nickname="Root",
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cli_create_super_admin_assigns_super_admin_role(superuser_db):
    """新建立的超管掛上超管角色, 而且有 auth_version (否則第一次重設密碼的 +1 會從缺值開始)。"""
    from modules.users.model import UserTable

    created = await in_session(
        lambda: superuser.create_super_admin(form_data=_super_admin_form())
    )

    async with session_scope():
        detail = await UserTable.find_detail_by_id(created.id)
        assert detail is not None
        assert detail["username"] == "root"
        assert detail["role_ids"] == [superuser_db]
        assert detail["permissions"] == ["*"]

        row = await UserTable.find_by_id(created.id)
        assert row is not None
        assert row.auth_version == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cli_create_super_admin_allows_a_second_one(superuser_db):
    """沒有「只能一次」的限制: 第二個超管、唯一超管失聯時的救援都走這一條。"""
    from modules.users.model import UserTable

    await in_session(lambda: superuser.create_super_admin(form_data=_super_admin_form("first")))
    await in_session(lambda: superuser.create_super_admin(form_data=_super_admin_form("second")))

    assert await count(UserTable) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cli_create_super_admin_rejects_duplicate_username(superuser_db):
    from modules.users.model import UserTable

    await in_session(lambda: superuser.create_super_admin(form_data=_super_admin_form()))

    with pytest.raises(LangException) as exc_info:
        await in_session(lambda: superuser.create_super_admin(form_data=_super_admin_form()))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == UserError.USERNAME_EXISTS.value.zh
    assert await count(UserTable) == 1
