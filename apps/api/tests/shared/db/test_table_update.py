"""`update_by_id` 只寫真的有變的欄位, 全都沒變時丟 `NoChangeError` (由平台轉成 204)。

比對要看值不看型別: UUID 欄位從資料庫讀回來是 `uuid.UUID`, 呼叫端傳的是字串。
少了這層正規化, 每次「原封不動地存檔」都會被當成一次更新, 前端也就永遠看不到「沒有變更」。
"""

import uuid

import pytest

from shared.http.errors import NoChangeError

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_update_without_real_change_raises_no_change(ref_rows):
    created = await ref_rows.create(data={"name": "原名"})

    with pytest.raises(NoChangeError):
        await ref_rows.update_by_id(created["id"], {"name": "原名"})

    updated = await ref_rows.update_by_id(created["id"], {"name": "新名"})
    assert updated is not None
    assert updated["name"] == "新名"


async def test_update_compares_uuid_and_uuid_list_by_value(ref_rows):
    owner, member = str(uuid.uuid4()), str(uuid.uuid4())
    created = await ref_rows.create(
        data={"name": "參照", "owner_id": owner, "member_ids": [owner, member]}
    )

    with pytest.raises(NoChangeError):
        await ref_rows.update_by_id(
            created["id"], {"owner_id": owner, "member_ids": [owner, member]}
        )

    updated = await ref_rows.update_by_id(created["id"], {"member_ids": [member]})
    assert updated is not None
    assert updated["member_ids"] == [member]


async def test_write_with_invalid_uuid_raises_value_error(ref_rows):
    """打錯的外鍵要當場失敗, 不能被靜靜跳過而變成「這個欄位沒寫進去」。"""
    with pytest.raises(ValueError, match="owner_id"):
        await ref_rows.create(data={"name": "壞的", "owner_id": "not-a-uuid"})


async def test_update_unknown_or_malformed_id_returns_none(ref_rows):
    """查無此筆回 None, 由 service 轉成 404; 格式不合法的 id 也一樣, 不能變成 500。"""
    assert await ref_rows.update_by_id(str(uuid.uuid4()), {"name": "x"}) is None
    assert await ref_rows.update_by_id("not-a-uuid", {"name": "x"}) is None
