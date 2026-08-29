"""各模組宣告的 Detail TypedDict，必須與查詢實際吐出來的欄位相符。

**這份測試守的是 `cast` 的空頭支票。** 每個模組的 finder 都在單一接縫用
`cast(XxxDetail, ...)` 宣告輸出形狀（見 `modules/*/model.py`），但 `cast` 不做任何
執行期檢查，mypy 也只是照單全收。於是「改了 `to_detail()`、少吐一個欄位」這件事
會是：mypy 靜悄悄、單元測試全綠，直到執行期才變成 `KeyError` → 500。

route 測試也擋不住 —— `tests/modules/conftest.py` 的 `set_current_users` 會把
`current_user_resolver` 整個換掉，所以那些測試從來沒有真的跑過
`UserTable.find_detail_by_username`。

要驗證「型別宣告 == 資料庫實際回傳」只有一條路：連上真的 PostgreSQL 跑真正的查詢，
再拿 `__required_keys__` 去對。因此這裡標成 integration（本機沒有資料庫會自動 skip，
CI 上會真的跑）。

新增模組時，只要它的 finder 有 `cast`，就在這裡加一條對應的測試。
**移除模組時要反過來做**：這裡的 import 在 module 層級，留著一個已刪除的模組會讓整個
後端測試在 collection 階段就 ImportError（標成 integration 也擋不住，collection 早於
marker 篩選）。移除清單見 `docs/architecture.md` 的「移除 module」。
"""

import os
from collections.abc import Mapping

import pytest
import pytest_asyncio
from sqlalchemy import delete

from modules.items.model import ItemDetail, ItemTable
from modules.push.model import PushSubscriptionDetail, PushSubscriptionTable
from modules.roles.model import RoleDetail, RoleTable
from modules.users.model import UserDetail, UserTable
from shared.auth.contracts import CurrentUser
from shared.db.session import configure_session_factory, create_engine, session_scope
from shared.db.table import BaseTable
from tests.integration import require_postgres

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

# 刪除順序與建立順序相反：外鍵不允許先刪掉還有人參照的那一張。
_CLEANUP_ORDER = [PushSubscriptionTable, ItemTable, UserTable, RoleTable]


@pytest_asyncio.fixture
async def db():
    """連上真的 PostgreSQL、建好正式 model 的資料表並清空；沒有可用的資料庫就跳過。

    連線邏輯與 `tests/shared/conftest.py` 的 `_connect` 相同，但那一份綁死在 shared 自己的
    測試資料表上（刻意的，見該檔說明），所以這裡另外建一個帶正式 model 的。
    """
    url = os.environ["POSTGRES_URL"]
    engine = create_engine(url)
    await require_postgres(engine, url)

    async with engine.begin() as connection:
        # 整份 metadata 一起建：正式 model 之間有外鍵（items → users、user_roles →
        # roles），只挑其中幾張會建不起來。
        await connection.run_sync(BaseTable.metadata.create_all)
        await _truncate(connection)

    configure_session_factory(engine)
    try:
        async with session_scope():
            yield
    finally:
        async with engine.begin() as connection:
            await _truncate(connection)
        await engine.dispose()


async def _truncate(connection) -> None:
    from modules.users.model import user_roles

    await connection.execute(user_roles.delete())
    for model in _CLEANUP_ORDER:
        await connection.execute(delete(model))


def _assert_covers(declared: type, actual: Mapping[str, object], label: str) -> None:
    """實際回傳的 dict 要涵蓋型別宣告的每一個必填鍵。

    只檢查「宣告的都在」，不檢查「回傳的都有宣告」—— model 本來就會多帶
    `created_at` 這類沒人讀的欄位，把它們也逼進 TypedDict 只會讓型別變成
    資料表定義的副本，那正是這些 TypedDict 刻意不做的事。
    """
    missing = set(declared.__required_keys__) - set(actual)  # type: ignore[attr-defined]
    assert not missing, f"{label} 少了這些欄位：{sorted(missing)}（實際有 {sorted(actual)}）"


async def test_current_user_matches_the_resolver_output(db):
    """`find_detail_by_username` 就是身分來源，它的輸出要撐得起 `CurrentUser`。

    少一個欄位的後果不是「某個畫面怪怪的」，而是每一個帶 token 的請求都 500 ——
    `shared/auth/dependency.py` 直接讀 `auth_version`、`permissions`、`is_disabled`。
    """
    await UserTable.create(
        data={"username": "contract-user", "password": "hashed", "nickname": "契約"}
    )

    result = await UserTable.find_detail_by_username("contract-user")

    assert result is not None
    _assert_covers(CurrentUser, result, "CurrentUser")


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
    _assert_covers(UserDetail, result, "UserDetail")


async def test_role_detail_matches_both_finders(db):
    created = await RoleTable.create(data={"name": "契約角色", "permissions": []})

    by_id = await RoleTable.find_detail_by_id(created["id"])
    by_ids = await RoleTable.find_details_by_ids([created["id"]])

    assert by_id is not None
    _assert_covers(RoleDetail, by_id, "RoleDetail（find_detail_by_id）")
    assert len(by_ids) == 1
    _assert_covers(RoleDetail, by_ids[0], "RoleDetail（find_details_by_ids）")


async def test_item_detail_matches_create_and_find(db):
    """`create()` 的回傳也在契約裡 —— `items` 的 service 直接讀它的 `name` 發 WS 事件。"""
    created = await ItemTable.create(data={"name": "契約項目"})
    _assert_covers(ItemDetail, created, "ItemDetail（create）")

    found = await ItemTable.find_detail_by_id(created["id"])

    assert found is not None
    _assert_covers(ItemDetail, found, "ItemDetail（find_detail_by_id）")


async def test_push_subscription_detail_matches_finders(db):
    owner = await UserTable.create(
        data={"username": "push-owner", "password": "hashed", "nickname": "訂閱者"}
    )
    await PushSubscriptionTable.create(
        data={
            "user_id": owner["id"],
            "endpoint": "https://push.example/x",
            "p256dh": "key",
            "auth": "secret",
        }
    )

    by_endpoint = await PushSubscriptionTable.find_detail_by_endpoint("https://push.example/x")
    by_user = await PushSubscriptionTable.find_details_by_user_id(owner["id"])
    all_details = await PushSubscriptionTable.find_all_details()

    assert by_endpoint is not None
    _assert_covers(PushSubscriptionDetail, by_endpoint, "PushSubscriptionDetail（by endpoint）")
    assert len(by_user) == 1
    _assert_covers(PushSubscriptionDetail, by_user[0], "PushSubscriptionDetail（by user）")
    assert len(all_details) == 1
    _assert_covers(PushSubscriptionDetail, all_details[0], "PushSubscriptionDetail（all）")


async def test_user_permissions_come_only_from_enabled_roles(db):
    """`role_ids` 列出全部角色，`permissions` 只聯集未停用的那些。

    停用一個角色要能立刻收回權限，但不該讓它從使用者的角色清單上消失 ——
    兩者混在一起的話，停用角色會讓管理畫面上的指派看起來被清空了。
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
