"""roles 宣告的 `RoleDetail`, 必須與兩個 finder 實際吐出來的欄位相符。

理由見 `tests/modules/users/test_model.py`: `cast` 不做執行期檢查, 只有連上真的資料庫跑
查詢才驗得到。標成 integration, 本機沒有資料庫會自動 skip, CI 上會真的跑。
"""

import pytest
from sqlalchemy.exc import IntegrityError

from modules.roles.model import RoleDetail, RoleTable
from shared.db.session import active_session
from shared.db.table import PagedResult, SimpleListResult, is_unique_violation

from ..helpers import assert_covers

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_role_detail_matches_both_finders(db):
    created = await RoleTable.create(data={"name": "契約角色", "permissions": []})

    by_id = await RoleTable.find_detail_by_id(created["id"])
    by_ids = await RoleTable.find_details_by_ids([created["id"]])

    assert by_id is not None
    assert_covers(RoleDetail, by_id, "RoleDetail（find_detail_by_id）")
    assert len(by_ids) == 1
    assert_covers(RoleDetail, by_ids[0], "RoleDetail（find_details_by_ids）")


async def test_role_name_is_unique(db):
    """service 的先查只擋得住依序來的請求, 同時到的兩個要靠資料庫的唯一約束。"""
    created = await RoleTable.create(data={"name": "重複角色", "permissions": []})

    found = await RoleTable.find_detail_by_name("重複角色")
    assert found is not None
    assert found["id"] == created["id"]
    assert_covers(RoleDetail, found, "RoleDetail（find_detail_by_name）")

    with pytest.raises(IntegrityError) as exc_info:
        await RoleTable.create(data={"name": "重複角色", "permissions": [], "is_disabled": True})
    assert is_unique_violation(exc_info.value)
    # 違反約束後 session 停在失敗狀態, 不先回滾的話 fixture 清資料時會拋 PendingRollbackError。
    await active_session().rollback()


def _names(result: PagedResult | SimpleListResult) -> list[str]:
    return sorted(role["name"] for role in result["list_data"])


async def test_find_list_filters_by_name_and_disabled_status(db):
    await RoleTable.create(data={"name": "編輯者", "permissions": []})
    await RoleTable.create(data={"name": "檢視者", "permissions": []})
    await RoleTable.create(data={"name": "舊編輯", "permissions": [], "is_disabled": True})

    assert _names(await RoleTable.find_list(limit=20, name="編輯")) == ["編輯者", "舊編輯"]
    assert _names(await RoleTable.find_list(limit=20, is_disabled=True)) == ["舊編輯"]
    assert _names(await RoleTable.find_list(limit=20, name="編輯", is_disabled=False)) == ["編輯者"]


async def test_find_options_filters_by_disabled_status(db):
    """下拉選單通常只要啟用中的角色; 不帶條件時列全部。"""
    await RoleTable.create(data={"name": "啟用", "permissions": []})
    await RoleTable.create(data={"name": "停用", "permissions": [], "is_disabled": True})

    assert _names(await RoleTable.find_options(is_disabled=False)) == ["啟用"]
    assert _names(await RoleTable.find_options()) == ["停用", "啟用"]


async def test_get_system_role_id_seeds_when_missing(db):
    """系統角色被誤刪或還沒 seed 時自己補回來, 而不是讓建立超管的指令失敗。"""
    assert await RoleTable.find_detail_by_code("super_admin") is None

    role_id = await RoleTable.get_super_admin_role_id()

    seeded = await RoleTable.find_detail_by_code("super_admin")
    assert seeded is not None
    assert seeded["id"] == role_id
    assert await RoleTable.get_super_admin_role_id() == role_id
