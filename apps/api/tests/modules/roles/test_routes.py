import pytest
from httpx import AsyncClient

from app.permissions import Permission
from modules.roles import service as role_service

from ..helpers import authenticate

USERS = {
    "role-reader": {
        "id": "user-role-reader",
        "nickname": "Role Reader",
        "role_ids": [],
        "permissions": [Permission.ROLE_READ],
        "is_disabled": False,
    },
}


@pytest.fixture(autouse=True)
def _current_users(set_current_users):
    set_current_users(USERS)


@pytest.mark.asyncio
async def test_get_roles_without_token_returns_401(client: AsyncClient):
    response = await client.get("/api/roles/")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_roles_requires_limit(client: AsyncClient):
    """`/roles/` 只有分頁一種形狀，所以 limit 是必填。

    非分頁的完整清單走 `/roles/options`，避免同一端點依參數回傳不同形狀。
    """
    authenticate(client, "role-reader")

    response = await client.get("/api/roles/")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_role_options_returns_simple_list_shape(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """`/roles/options` 回傳 `{list_data, count}`，且不含任何游標欄位。"""

    async def fake_get_role_options(is_disabled=None):
        return {
            "list_data": [
                {
                    "id": "role-1",
                    "code": None,
                    "name": "Reader",
                    "permissions": [Permission.ROLE_READ],
                    "is_disabled": False,
                }
            ],
            "count": 1,
        }

    monkeypatch.setattr(role_service, "get_role_options", fake_get_role_options)

    authenticate(client, "role-reader")

    response = await client.get("/api/roles/options")

    assert response.status_code == 200
    assert response.json() == {
        "list_data": [
            {
                "id": "role-1",
                "code": None,
                "name": "Reader",
                "permissions": ["roles:read"],
                "is_disabled": False,
            }
        ],
        "count": 1,
    }


def test_get_role_options_is_not_shadowed_by_id_route():
    """`/roles/options` 必須宣告在 `/roles/{id}` 之前。

    FastAPI 依宣告順序比對路由，順序反過來的話 "options" 會被 `/{id}` 先吃掉，
    然後 `UuidText` 會將它判成 422。
    """
    # 直接檢查 APIRouter 的公開 `.routes`，取得本模組定義的路徑及其宣告順序。
    from modules.roles.router import router

    # 用 getattr 取值而不是 route.path：Starlette 的 `BaseRoute` 基底類別沒有 `path`
    # 屬性（只有 Route/WebSocketRoute 等子類有），直接存取會讓 mypy 報錯。
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
                    "permissions": [Permission.ROLE_READ],
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

    authenticate(client, "role-reader")

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
                "permissions": ["roles:read"],
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
    authenticate(client, "role-reader")

    response = await client.get("/api/roles/not-an-object-id")

    assert response.status_code == 422
