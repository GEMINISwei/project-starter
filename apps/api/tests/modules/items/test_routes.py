"""**範例模組**的路由測試。移除範例時整個檔案一併刪除。

這裡驗的是「路由掛載 + 權限把關 + 回應形狀」這三件事，Document 一律 stub 掉 ——
需要真的資料庫的分頁行為由 `tests/shared/test_pagination.py`（integration）負責，
不必每個模組再測一次。
"""

import pytest
from httpx import AsyncClient

from app.permissions import Permission
from modules.items import service as item_service
from modules.items.model import ItemTable

from ..helpers import authenticate

USERS = {
    "item-reader": {
        "id": "user-item-reader",
        "nickname": "Item Reader",
        "role_ids": [],
        "permissions": [Permission.ITEM_READ],
        "is_disabled": False,
    },
    "item-manager": {
        "id": "user-item-manager",
        "nickname": "Item Manager",
        "role_ids": [],
        # 只給聚合權限，驗證 dependencies 展開之後真的拿得到 create/update/delete。
        "permissions": [Permission.ITEM_MANAGE],
        "is_disabled": False,
    },
    "nobody": {
        "id": "user-nobody",
        "nickname": "Nobody",
        "role_ids": [],
        "permissions": [],
        "is_disabled": False,
    },
}


# 格式合法但不存在的 id。要真的是合法 UUID —— 隨手打一個字串會被 `UuidText`
# 擋成 422，那條測試就變成在驗 422 而不是 404。
MISSING_ID = "0123abcd-4567-89ab-cdef-0123456789ab"


@pytest.fixture(autouse=True)
def _current_users(set_current_users):
    set_current_users(USERS)


@pytest.mark.asyncio
async def test_get_items_without_token_returns_401(client: AsyncClient):
    response = await client.get("/api/items/")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_items_without_permission_returns_403(client: AsyncClient):
    authenticate(client, "nobody")

    response = await client.get("/api/items/", params={"limit": 10})

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_items_requires_limit(client: AsyncClient):
    """`/items/` 只有分頁一種形狀，所以 limit 是必填（見 PaginationParams）。"""
    authenticate(client, "item-reader")

    response = await client.get("/api/items/")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_items_returns_paginated_shape(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_get_item_list(
        cursor=None, direction="next", limit=None, name=None, is_disabled=None
    ):
        assert limit == 10
        assert name == "螺絲"
        assert is_disabled is False
        return {
            "list_data": [
                {
                    "id": "item-1",
                    "name": "螺絲",
                    "description": "M3 十字",
                    "is_disabled": False,
                    "created_by_nickname": "Item Manager",
                }
            ],
            "next_cursor": None,
            "prev_cursor": None,
            "has_next": False,
            "has_previous": False,
            "total_count": 1,
        }

    monkeypatch.setattr(item_service, "get_item_list", fake_get_item_list)
    authenticate(client, "item-reader")

    response = await client.get(
        "/api/items/",
        params={"limit": 10, "name": "螺絲", "is_disabled": "false"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["list_data"][0]["name"] == "螺絲"
    # created_by_nickname 不是 items 表的欄位，是 $lookup 補上的 —— 要能通過 response_model。
    assert body["list_data"][0]["created_by_nickname"] == "Item Manager"
    assert body["total_count"] == 1


@pytest.mark.asyncio
async def test_get_item_with_invalid_id_returns_422(client: AsyncClient):
    authenticate(client, "item-reader")

    response = await client.get("/api/items/not-an-object-id")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_missing_item_returns_404(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    async def fake_find_detail_by_id(id):
        return None

    monkeypatch.setattr(ItemTable, "find_detail_by_id", fake_find_detail_by_id)
    authenticate(client, "item-reader")

    response = await client.get(f"/api/items/{MISSING_ID}")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_item_requires_create_permission(client: AsyncClient):
    """只有讀權限不能建立。"""
    authenticate(client, "item-reader")

    response = await client.post("/api/items/", json={"name": "新項目", "description": ""})

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_item_rejects_blank_name(client: AsyncClient):
    """`NonEmptyText` 會擋下只有空白的名稱 —— 不要讓它變成一筆看不見的資料。"""
    authenticate(client, "item-manager")

    response = await client.post("/api/items/", json={"name": "   ", "description": ""})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_item_with_aggregate_permission_succeeds(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """持有 ITEM_MANAGE 就該能建立 —— 驗證 dependencies 的展開有生效。"""
    captured = {}

    async def fake_create_item(form_data, current_user_id):
        captured["form_data"] = form_data
        captured["current_user_id"] = current_user_id
        return {"id": "item-new"}

    monkeypatch.setattr(item_service, "create_item", fake_create_item)
    authenticate(client, "item-manager")

    response = await client.post("/api/items/", json={"name": "  新項目  ", "description": "說明"})

    assert response.status_code == 200
    assert response.json() == {"id": "item-new"}
    # NonEmptyText 會 strip 前後空白。service 收的是 pydantic model 本身（不是 dict），
    # 所以這裡用屬性存取 —— 欄位名打錯會被 mypy 擋下來，不會等到執行時才炸。
    assert captured["form_data"].name == "新項目"
    # 建立者取自 token 對應的使用者，不是由呼叫端指定 —— 否則可以偽造他人身分。
    assert captured["current_user_id"] == "user-item-manager"


@pytest.mark.asyncio
async def test_delete_item_requires_delete_permission(client: AsyncClient):
    authenticate(client, "item-reader")

    response = await client.delete(f"/api/items/{MISSING_ID}")

    assert response.status_code == 403
