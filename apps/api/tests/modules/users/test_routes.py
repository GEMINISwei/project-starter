from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.permissions import Permission
from modules.users import service as user_service
from modules.users.model import UserTable
from modules.users.service import UserError

from ..helpers import authenticate

USERS = {
    "manager": {
        "id": "user-manager",
        "nickname": "Manager",
        "role_ids": [],
        "permissions": [Permission.USER_MANAGE],
        "is_disabled": False,
    },
    "reader": {
        "id": "user-reader",
        "nickname": "Reader",
        "role_ids": [],
        "permissions": [Permission.USER_READ],
        "is_disabled": False,
    },
    "creator": {
        "id": "user-creator",
        "nickname": "Creator",
        "role_ids": [],
        "permissions": [Permission.USER_CREATE],
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


@pytest.fixture(autouse=True)
def _current_users(set_current_users):
    set_current_users(USERS)


@pytest.mark.asyncio
async def test_get_users_me_without_token_returns_401(client: AsyncClient):
    response = await client.get("/api/users/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_users_me_with_valid_token_returns_current_user(client: AsyncClient):
    authenticate(client, "reader")

    response = await client.get("/api/users/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": "user-reader",
        "nickname": "Reader",
        "role_ids": [],
        "permissions": ["users:read"],
    }


@pytest.mark.asyncio
async def test_get_users_without_permission_returns_403(client: AsyncClient):
    authenticate(client, "viewer")

    response = await client.get("/api/users/")

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_users_without_limit_returns_422(client: AsyncClient):
    authenticate(client, "reader")

    response = await client.get("/api/users/")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_users_with_read_permission_returns_list(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_get_user_list(
        cursor=None, direction="next", limit=None, name=None, role_id=None, is_disabled=None
    ):
        return {
            "list_data": [
                {
                    "id": "user-1",
                    "username": "alice",
                    "nickname": "Alice",
                    "role_ids": [],
                    "permissions": [Permission.USER_READ],
                    "is_disabled": False,
                }
            ],
            "next_cursor": None,
            "prev_cursor": None,
            "has_next": False,
            "has_previous": False,
            "total_count": 1,
        }

    monkeypatch.setattr(user_service, "get_user_list", fake_get_user_list)

    authenticate(client, "reader")

    response = await client.get("/api/users/", params={"limit": 20})

    assert response.status_code == 200
    assert response.json() == {
        "list_data": [
            {
                "id": "user-1",
                "username": "alice",
                "nickname": "Alice",
                "role_ids": [],
                "permissions": ["users:read"],
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
async def test_post_users_missing_required_fields_returns_422(client: AsyncClient):
    authenticate(client, "creator")

    response = await client.post(
        "/api/users/",
        json={"username": "new-user"},
    )

    assert response.status_code == 422
    errors = response.json()["detail"]
    assert {tuple(error["loc"]) for error in errors} == {
        ("body", "password"),
        ("body", "nickname"),
    }


@pytest.mark.asyncio
async def test_post_users_without_create_permission_returns_403(client: AsyncClient):
    authenticate(client, "viewer")

    response = await client.post(
        "/api/users/",
        json={
            "username": "new-user",
            "password": "password123",
            "nickname": "New User",
            "role_ids": [],
        },
    )

    assert response.status_code == 403


# 「查無此人」必須是 404。少了服務層的存在性檢查，`update_by_id` 會回傳 None，
# 再撞上 response_model 的必填 `id` 變成 ResponseValidationError（500）——
# 也就是把「客戶端給錯 id」報成「伺服器壞了」。
MISSING_ID = "0123abcd-4567-89ab-cdef-0123456789ab"


@pytest.mark.asyncio
async def test_patch_missing_user_returns_404(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(UserTable, "find_detail_by_id", AsyncMock(return_value=None))
    authenticate(client, "manager")

    response = await client.patch(
        f"/api/users/{MISSING_ID}",
        json={"nickname": "Whoever", "is_disabled": False},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reset_password_of_missing_user_returns_404(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(UserTable, "find_detail_by_id", AsyncMock(return_value=None))
    authenticate(client, "manager")

    response = await client.patch(
        f"/api/users/{MISSING_ID}/reset_password",
        json={"password": "new-password-123"},
    )

    assert response.status_code == 404


# --- 登入限流（路由層） ----------------------------------------------------
#
# shared 的單元測試已經涵蓋 RateLimiter 本身。這裡守的是**接起來之後**才成立的事：
# LangException 帶的 Retry-After 有沒有真的通過 FastAPI 的 exception handler 變成 HTTP
# 回應標頭，以及限流 key 是不是真的取自不可偽造的來源。


@pytest.fixture
def _clean_login_limiter():
    """限流器是 module-level 的共用狀態，測試之間必須互不影響。"""
    from modules.users.router import login_limiter

    login_limiter.clear()
    yield login_limiter
    login_limiter.clear()


@pytest.fixture
def _login_always_fails(monkeypatch: pytest.MonkeyPatch):
    """讓登入固定失敗，且不碰資料庫與 bcrypt。

    限流的計數只在「沒有成功」時累積（成功會 reset），所以測試需要的是穩定的失敗。
    直接替換 login_user 也順便避開 bcrypt —— 真的跑十幾次雜湊會讓這個測試慢好幾秒。
    """
    from shared.http.errors import LangException

    async def always_fails(form_data, env):
        raise LangException(401, UserError.INVALID_CREDENTIALS)

    monkeypatch.setattr(user_service, "login_user", always_fails)


@pytest.mark.asyncio
async def test_login_rate_limit_returns_429_with_retry_after(
    client: AsyncClient, _clean_login_limiter, _login_always_fails
):
    limiter = _clean_login_limiter
    payload = {"username": "victim", "password": "wrong"}

    for _ in range(limiter.max_attempts):
        response = await client.post("/api/users/login", data=payload)
        assert response.status_code == 401

    response = await client.post("/api/users/login", data=payload)

    assert response.status_code == 429
    # 這一行是重點：單元測試只能證明例外物件上有這個標頭，證明不了它會出現在回應上。
    assert "retry-after" in response.headers
    assert int(response.headers["retry-after"]) >= 1


@pytest.mark.asyncio
async def test_forged_forwarded_header_cannot_bypass_login_rate_limit(
    client: AsyncClient, _clean_login_limiter, _login_always_fails
):
    """每次換一個假的 X-Forwarded-For 也不能重新取得額度。

    限流 key 只信任 nginx 設定的 X-Real-IP，不能受用戶端提供的 header 影響。
    """
    limiter = _clean_login_limiter
    payload = {"username": "victim", "password": "wrong"}

    for i in range(limiter.max_attempts):
        response = await client.post(
            "/api/users/login",
            data=payload,
            headers={"X-Forwarded-For": f"1.2.3.{i}"},
        )
        assert response.status_code == 401

    response = await client.post(
        "/api/users/login",
        data=payload,
        headers={"X-Forwarded-For": "9.9.9.9"},
    )

    assert response.status_code == 429


# --- Session 撤銷（auth_version） -------------------------------------------
#
# `auth_version` 讓重設密碼只撤銷目標使用者的既有 session；TOKEN_VERSION 則保留給全域撤銷。


def _token_with_auth_version(username: str, auth_version: int) -> str:
    from app.server import app
    from shared.auth.contracts import TokenSubject
    from shared.auth.tokens import create_token

    payload: TokenSubject = {"username": username, "auth_version": auth_version}
    return create_token(payload, app.state.env)["access_token"]


@pytest.mark.asyncio
async def test_token_with_stale_auth_version_is_rejected(client: AsyncClient, set_current_users):
    """重設密碼把 auth_version +1 之後，舊 token 立刻失效。"""
    set_current_users({"manager": {**USERS["manager"], "auth_version": 2}})

    client.cookies.set("access_token", _token_with_auth_version("manager", 1))
    response = await client.get("/api/users/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_token_with_current_auth_version_is_accepted(client: AsyncClient, set_current_users):
    set_current_users({"manager": {**USERS["manager"], "auth_version": 2}})

    client.cookies.set("access_token", _token_with_auth_version("manager", 2))
    response = await client.get("/api/users/me")

    assert response.status_code == 200
