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

import pytest

from modules.roles.public import RoleTable
from modules.users.model import UserDetail, UserTable
from shared.auth.contracts import CurrentUser

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
    await UserTable.create(
        data={"username": "no-leak", "password": "hashed", "nickname": "不外洩"}
    )

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
