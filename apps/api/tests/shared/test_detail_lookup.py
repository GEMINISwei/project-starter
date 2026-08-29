"""驗證 `BaseTable.find_detail_by_id` 的查詢契約。

此測試需要真的 PostgreSQL，因為條件、載入與 `to_detail()` 的組合只有在資料庫執行時
才能驗證。它使用測試專屬的 `DetailRow`（見 conftest）確認所有繼承 `BaseTable` 的
model 都遵守以下規則：依 id 取回指定那一列、套用 `to_detail()`，並在找不到或 id
格式錯誤時回傳 None。
"""

import uuid

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_find_detail_by_id_returns_the_requested_row(detail_rows):
    """依 id 查詢時，回傳資料必須與指定那一列一致。"""
    model, ids = detail_rows

    result = await model.find_detail_by_id(ids[1])

    assert result is not None
    assert result["name"] == "detail-1"
    assert result["id"] == ids[1]


async def test_find_detail_by_id_applies_to_detail(detail_rows):
    """子類別覆寫的 `to_detail()` 要有被套用。"""
    model, ids = detail_rows

    result = await model.find_detail_by_id(ids[2])

    assert result is not None
    assert result["label"] == "#detail-2"


async def test_find_detail_by_id_returns_none_for_missing_id(detail_rows):
    """格式合法但不存在的 id 要回傳 None —— 這是 `ensure_found` 能回 404 的前提。"""
    model, _ = detail_rows

    assert await model.find_detail_by_id(str(uuid.uuid4())) is None


async def test_find_detail_by_id_returns_none_for_malformed_id(detail_rows):
    """格式不合法的 id 回傳 None 而不是丟例外（與 `find_by_id` 一致）。

    路由層的 `UuidText` 已經先擋一道，但 model 不該假設呼叫端一定是路由 ——
    service 之間互相呼叫時傳進來的 id 可能來自其他資料表的參照。
    """
    model, _ = detail_rows

    assert await model.find_detail_by_id("not-a-uuid") is None
