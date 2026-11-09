import pytest
from httpx import AsyncClient

from app.permissions import Permission
from modules.roles import service as role_service

from ..helpers import authenticate

USERS = {
    "super": {
        "id": "user-super",
        "nickname": "Super",
        "role_ids": [],
        "permissions": [Permission.ALL],
        "is_disabled": False,
    },
    "viewer": {
        "id": "user-viewer",
        "nickname": "Viewer",
        "role_ids": [],
        "permissions": [],
        "is_disabled": False,
    },
}

ROLE_ID = "0123abcd-4567-89ab-cdef-0123456789ab"
# 後台 (角色管理) 只開放給超級管理者, 沒有任何一個權限能打開這些端點。
ADMIN_ROUTES = [
    ("GET", "/api/roles/?limit=20", None),
    ("GET", "/api/roles/options", None),
    ("GET", "/api/roles/permission-options", None),
    ("GET", f"/api/roles/{ROLE_ID}", None),
    ("POST", "/api/roles/", {"name": "編輯", "permissions": []}),
    ("PATCH", f"/api/roles/{ROLE_ID}", {"name": "編輯", "permissions": [], "is_disabled": False}),
    ("DELETE", f"/api/roles/{ROLE_ID}", None),
]


@pytest.fixture(autouse=True)
def _current_users(set_current_users):
    set_current_users(USERS)


@pytest.mark.asyncio
async def test_get_roles_without_token_returns_401(client: AsyncClient):
    response = await client.get("/api/roles/")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_roles_requires_limit(client: AsyncClient):
    """`/roles/` 只有分頁一種形狀, 所以 limit 是必填。

    非分頁的完整清單走 `/roles/options`, 避免同一端點依參數回傳不同形狀。
    """
    authenticate(client, "super")

    response = await client.get("/api/roles/")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_role_options_returns_simple_list_shape(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """`/roles/options` 回傳 `{list_data, count}`, 且不含任何游標欄位。"""

    async def fake_get_role_options(is_disabled=None):
        return {
            "list_data": [
                {
                    "id": "role-1",
                    "code": None,
                    "name": "Reader",
                    "permissions": [],
                    "is_disabled": False,
                }
            ],
            "count": 1,
        }

    monkeypatch.setattr(role_service, "get_role_options", fake_get_role_options)

    authenticate(client, "super")

    response = await client.get("/api/roles/options")

    assert response.status_code == 200
    assert response.json() == {
        "list_data": [
            {
                "id": "role-1",
                "code": None,
                "name": "Reader",
                "permissions": [],
                "is_disabled": False,
            }
        ],
        "count": 1,
    }


def test_get_role_options_is_not_shadowed_by_id_route():
    """`/roles/options` 必須宣告在 `/roles/{id}` 之前。

    FastAPI 依宣告順序比對路由, 順序反過來的話 "options" 會被 `/{id}` 先吃掉,
    然後 `UuidText` 會將它判成 422。
    """
    # 直接檢查 APIRouter 的公開 `.routes`, 取得本模組定義的路徑及其宣告順序。
    from modules.roles.router import router

    # 用 getattr 取值而不是 route.path: Starlette 的 `BaseRoute` 基底類別沒有 `path`
    # 屬性 (只有 Route/WebSocketRoute 等子類有), 直接存取會讓 mypy 報錯。
    paths = [getattr(route, "path", "") for route in router.routes]

    assert paths.index("/roles/options") < paths.index("/roles/{id}")


@pytest.mark.asyncio
async def test_get_roles_with_limit_returns_paginated_shape(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_get_role_list(
        cursor=None, direction="next", limit=None, name=None, is_disabled=None
    ):
        assert limit == 20
        assert name == "admin"
        assert is_disabled is False
        return {
            "list_data": [
                {
                    "id": "role-1",
                    "code": None,
                    "name": "Reader",
                    "permissions": [],
                    "is_disabled": False,
                }
            ],
            "next_cursor": None,
            "prev_cursor": None,
            "has_next": False,
            "has_previous": False,
            "total_count": 1,
        }

    monkeypatch.setattr(role_service, "get_role_list", fake_get_role_list)

    authenticate(client, "super")

    response = await client.get(
        "/api/roles/",
        params={"limit": 20, "name": "admin", "is_disabled": "false"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "list_data": [
            {
                "id": "role-1",
                "code": None,
                "name": "Reader",
                "permissions": [],
                "is_disabled": False,
            }
        ],
        "next_cursor": None,
        "prev_cursor": None,
        "has_next": False,
        "has_previous": False,
        "total_count": 1,
    }


@pytest.mark.asyncio
async def test_get_role_with_invalid_id_returns_422(client: AsyncClient):
    authenticate(client, "super")

    response = await client.get("/api/roles/not-an-object-id")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_permission_options_returns_labels_grouped_by_module(client: AsyncClient):
    """角色編輯畫面直接用這裡的 `category` 分組、`label` 顯示, 前端沒有第二份標籤。

    走真的權限目錄 (不 stub): 要驗的正是「每個啟用中的 module 都帶了分類與標籤」。
    """
    authenticate(client, "super")

    response = await client.get(
        "/api/roles/permission-options", headers={"Accept-Language": "en"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == len(body["list_data"])
    assert all(item["label"] and item["category"] for item in body["list_data"])
    # 萬用字元不能被勾選: 它只屬於 seed 出來的超級管理者角色。
    assert Permission.ALL not in {item["value"] for item in body["list_data"]}


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "url", "body"), ADMIN_ROUTES)
async def test_role_admin_routes_reject_non_super_admin(
    client: AsyncClient, method: str, url: str, body: dict | None
):
    authenticate(client, "viewer")

    response = await client.request(method, url, json=body)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_permission_options_requires_authentication(client: AsyncClient):
    response = await client.get("/api/roles/permission-options")

    assert response.status_code == 401
