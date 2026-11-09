"""users 宣告的 Detail TypedDict, 必須與查詢實際吐出來的欄位相符。

**這份測試守的是 `cast` 的空頭支票。** 每個模組的 finder 都在單一接縫用
`cast(XxxDetail, ...)` 宣告輸出形狀 (見 `modules/*/model.py`), 但 `cast` 不做任何
執行期檢查, mypy 也只是照單全收。於是「改了 `to_detail()`、少吐一個欄位」這件事
會是: mypy 靜悄悄、單元測試全綠, 直到執行期才變成 `KeyError` → 500。

route 測試也擋不住 —— `tests/modules/conftest.py` 的 `set_current_users` 會把
`current_user_resolver` 整個換掉, 所以那些測試從來沒有真的跑過
`UserTable.find_detail_by_username`。

要驗證「型別宣告 == 資料庫實際回傳」只有一條路: 連上真的 PostgreSQL 跑真正的查詢,
再拿 `__required_keys__` 去對。因此這裡標成 integration (本機沒有資料庫會自動 skip,
CI 上會真的跑)。

每個模組在自己的 `test_model.py` 驗自己的 finder (roles 的在 `tests/modules/roles/`),
刪掉模組時連同它的測試目錄整包刪除即可。
"""

import contextlib
from collections.abc import Iterator

import pytest
from sqlalchemy import event

from modules.roles.model import RoleTable
from modules.users.model import UserDetail, UserTable
from shared.auth.contracts import CurrentUser
from shared.db.session import active_session
from shared.db.table import PagedResult

from ..helpers import assert_covers

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_current_user_matches_the_resolver_output(db):
    """`find_detail_by_username` 就是身分來源, 它的輸出要撐得起 `CurrentUser`。

    少一個欄位的後果不是「某個畫面怪怪的」, 而是每一個帶 token 的請求都 500 ——
    `shared/auth/dependency.py` 直接讀 `auth_version`、`permissions`、`is_disabled`。
    """
    await UserTable.create(
        data={"username": "contract-user", "password": "hashed", "nickname": "契約"}
    )

    result = await UserTable.find_detail_by_username("contract-user")

    assert result is not None
    assert_covers(CurrentUser, result, "CurrentUser")


async def test_current_user_never_leaks_the_password_by_default(db):
    """`to_detail()` 預設要把 password 拿掉 —— 它會被放進 `GET /users/me` 的來源 dict。"""
    await UserTable.create(data={"username": "no-leak", "password": "hashed", "nickname": "不外洩"})

    result = await UserTable.find_detail_by_username("no-leak")

    assert result is not None
    assert "password" not in result


async def test_user_detail_matches_find_detail_by_id(db):
    created = await UserTable.create(
        data={"username": "detail-user", "password": "hashed", "nickname": "細節"}
    )

    result = await UserTable.find_detail_by_id(created["id"])

    assert result is not None
    assert_covers(UserDetail, result, "UserDetail")


async def test_user_permissions_come_only_from_enabled_roles(db):
    """`role_ids` 列出全部角色, `permissions` 只聯集未停用的那些。

    停用一個角色要能立刻收回權限, 但不該讓它從使用者的角色清單上消失 ——
    兩者混在一起的話, 停用角色會讓管理畫面上的指派看起來被清空了。
    """
    enabled = await RoleTable.create(data={"name": "啟用", "permissions": ["users:read"]})
    disabled = await RoleTable.create(
        data={"name": "停用", "permissions": ["users:create"], "is_disabled": True}
    )
    created = await UserTable.create(
        data={
            "username": "mixed-roles",
            "password": "hashed",
            "nickname": "混合",
            "role_ids": [enabled["id"], disabled["id"]],
        }
    )

    result = await UserTable.find_detail_by_id(created["id"])

    assert result is not None
    assert set(result["role_ids"]) == {enabled["id"], disabled["id"]}
    assert result["permissions"] == ["users:read"]


async def test_update_with_empty_role_ids_clears_roles(db):
    """後台把角色改成「未指派」送的是 `role_ids=[]`, 要真的把關聯清空, 不能被當成「沒有變」。"""
    role = await RoleTable.create(data={"name": "清空", "permissions": []})
    created = await UserTable.create(
        data={
            "username": "clear-roles",
            "password": "hashed",
            "nickname": "清空",
            "role_ids": [role["id"]],
        }
    )

    await UserTable.update_by_id(id=created["id"], data={"role_ids": []})

    result = await UserTable.find_detail_by_id(created["id"])
    assert result is not None
    assert result["role_ids"] == []


@contextlib.contextmanager
def count_queries() -> Iterator[list[str]]:
    """記下這段期間送到資料庫的每一條 SQL。"""
    engine = active_session().sync_session.get_bind()
    statements: list[str] = []

    def record(_connection, _cursor, statement, *_args) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", record)


async def test_find_detail_by_username_runs_three_queries(db):
    """身分來源每個請求都會跑: 使用者、自己的關聯表、roles 的公開介面, 固定三次。

    users 不能 JOIN roles 的資料表 (只能走 `modules.roles.public`), 所以比合在一起查多一次;
    這個測試鎖住的是「不會再多」—— 例如逐一查每個角色。
    """
    first = await RoleTable.create(data={"name": "甲", "permissions": ["users:read"]})
    second = await RoleTable.create(data={"name": "乙", "permissions": ["roles:read"]})
    await UserTable.create(
        data={
            "username": "three-queries",
            "password": "hashed",
            "nickname": "三次",
            "role_ids": [first["id"], second["id"]],
        }
    )

    with count_queries() as statements:
        result = await UserTable.find_detail_by_username("three-queries")

    assert result is not None
    assert result["permissions"] == ["roles:read", "users:read"]
    assert len(statements) == 3


async def test_find_list_query_count_does_not_grow_with_users(db):
    """列表一次補完整頁的角色, 查詢次數與這一頁有幾個人無關 (沒有 N+1)。"""
    role = await RoleTable.create(data={"name": "共用", "permissions": ["users:read"]})

    async def add_user(username: str) -> None:
        await UserTable.create(
            data={
                "username": username,
                "password": "hashed",
                "nickname": username,
                "role_ids": [role["id"]],
            }
        )

    await add_user("page-1")
    with count_queries() as one_user:
        await UserTable.find_list(limit=20)

    for index in range(2, 5):
        await add_user(f"page-{index}")
    with count_queries() as four_users:
        page = await UserTable.find_list(limit=20)

    assert len(page["list_data"]) == 4
    assert all(user["role_ids"] == [role["id"]] for user in page["list_data"])
    assert len(four_users) == len(one_user)


async def _user(username: str, nickname: str, **extra) -> dict:
    return await UserTable.create(
        data={"username": username, "password": "hashed", "nickname": nickname, **extra}
    )


def _usernames(page: PagedResult) -> list[str]:
    return sorted(user["username"] for user in page["list_data"])


async def test_find_list_filters_by_name(db):
    """暱稱的關鍵字篩選, 大小寫不敏感、部分符合即可。"""
    await _user("ming", "王小明")
    await _user("da", "王大明")
    await _user("li", "李四")

    assert _usernames(await UserTable.find_list(limit=20, name="小明")) == ["ming"]
    assert _usernames(await UserTable.find_list(limit=20, name="王")) == ["da", "ming"]


async def test_find_list_filters_by_role_and_unassigned(db):
    """指定角色只列掛著它的人; `unassigned` 列沒有任何角色的人; 格式錯的 id 列出零筆。"""
    role = await RoleTable.create(data={"name": "篩選", "permissions": []})
    await _user("with-role", "有角色", role_ids=[role["id"]])
    await _user("no-role", "沒角色")

    assert _usernames(await UserTable.find_list(limit=20, role_id=role["id"])) == ["with-role"]
    assert _usernames(await UserTable.find_list(limit=20, role_id="unassigned")) == ["no-role"]
    # 打錯的 id 若被忽略會回傳全部, 看起來像「所有人都掛著這個角色」。
    assert _usernames(await UserTable.find_list(limit=20, role_id="not-a-uuid")) == []


async def test_find_list_filters_by_disabled_status(db):
    await _user("active", "啟用中")
    await _user("disabled", "已停用", is_disabled=True)

    assert _usernames(await UserTable.find_list(limit=20, is_disabled=True)) == ["disabled"]
    assert _usernames(await UserTable.find_list(limit=20, is_disabled=False)) == ["active"]
    assert _usernames(await UserTable.find_list(limit=20)) == ["active", "disabled"]


async def test_update_unknown_user_returns_none(db):
    """查無此人回 None, 由 service 轉成 404; 格式不合法的 id 也一樣, 不能變成 500。"""
    assert await UserTable.update_by_id(id="0123abcd-4567-89ab-cdef-0123456789ab", data={}) is None
    assert await UserTable.update_by_id(id="not-a-uuid", data={"nickname": "x"}) is None
