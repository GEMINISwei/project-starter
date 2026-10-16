from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient

from app.permissions import Permission
from modules.users import account
from modules.users import service as user_service
from modules.users.errors import UserError
from modules.users.model import UserTable
from shared.auth import passwords

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


# 「查無此人」必須是 404。少了服務層的存在性檢查, `update_by_id` 會回傳 None,
# 再撞上 response_model 的必填 `id` 變成 ResponseValidationError (500) ——
# 也就是把「客戶端給錯 id」報成「伺服器壞了」。
MISSING_ID = "0123abcd-4567-89ab-cdef-0123456789ab"


@pytest.fixture(autouse=True)
def _current_users(set_current_users):
    set_current_users(USERS)


@pytest.mark.asyncio
async def test_get_users_me_without_token_returns_401(client: AsyncClient):
    response = await client.get("/api/users/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_users_me_with_valid_token_returns_current_user(client: AsyncClient):
    authenticate(client, "super")

    response = await client.get("/api/users/me")

    assert response.status_code == 200
    assert response.json() == {
        "id": "user-super",
        "nickname": "Super",
        "role_ids": [],
        "permissions": ["*"],
    }


# 後台 (使用者管理) 只開放給超級管理者: 角色上的權限是給一般帳號的業務功能用的,
# 沒有任何一個權限能打開這些端點。
ADMIN_ROUTES = [
    ("GET", "/api/users/?limit=20", None),
    ("GET", f"/api/users/{MISSING_ID}", None),
    (
        "POST",
        "/api/users/",
        {"username": "new-user", "password": "password123", "nickname": "New", "role_ids": []},
    ),
    ("PATCH", f"/api/users/{MISSING_ID}", {"nickname": "Whoever", "is_disabled": False}),
    ("PATCH", f"/api/users/{MISSING_ID}/reset-password", {"password": "new-password-123"}),
    ("DELETE", f"/api/users/{MISSING_ID}", None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("method", "url", "body"), ADMIN_ROUTES)
async def test_user_admin_routes_reject_non_super_admin(
    client: AsyncClient, method: str, url: str, body: dict | None
):
    authenticate(client, "viewer")

    response = await client.request(method, url, json=body)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_users_without_limit_returns_422(client: AsyncClient):
    authenticate(client, "super")

    response = await client.get("/api/users/")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_users_as_super_admin_returns_list(
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

    monkeypatch.setattr(user_service, "get_user_list", fake_get_user_list)

    authenticate(client, "super")

    response = await client.get("/api/users/", params={"limit": 20})

    assert response.status_code == 200
    assert response.json() == {
        "list_data": [
            {
                "id": "user-1",
                "username": "alice",
                "nickname": "Alice",
                "role_ids": [],
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
async def test_post_users_missing_required_fields_returns_422(client: AsyncClient):
    authenticate(client, "super")

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
async def test_patch_missing_user_returns_404(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(UserTable, "find_detail_by_id", AsyncMock(return_value=None))
    authenticate(client, "super")

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
    authenticate(client, "super")

    response = await client.patch(
        f"/api/users/{MISSING_ID}/reset-password",
        json={"password": "new-password-123"},
    )

    assert response.status_code == 404
    # 比對訊息: 路徑打錯時 FastAPI 也回 404, 只看狀態碼的話這條會在路由消失時照樣通過。
    assert response.json()["detail"] == UserError.NOT_FOUND.value.zh


@pytest.mark.asyncio
async def test_patch_me_writes_only_the_nickname_of_the_caller(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """不需要任何權限; 對象一定是發出請求的人自己, 多送的角色與停用狀態會被丟掉。"""
    update = AsyncMock(return_value={"id": USERS["viewer"]["id"]})
    monkeypatch.setattr(UserTable, "update_by_id", update)
    authenticate(client, "viewer")

    response = await client.patch(
        "/api/users/me",
        json={"nickname": "新暱稱", "role_ids": [MISSING_ID], "is_disabled": False},
    )

    assert response.status_code == 200
    update.assert_awaited_once_with(id=USERS["viewer"]["id"], data={"nickname": "新暱稱"})


@pytest.mark.asyncio
async def test_logout_revokes_sessions_of_the_current_user_only(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    """撤銷的對象一定是發出請求的人自己 —— id 從 token 來, 不從請求內容來。"""
    revoke = AsyncMock(return_value={"id": "user-viewer", "auth_version": 2})
    monkeypatch.setattr(UserTable, "revoke_sessions", revoke)
    authenticate(client, "viewer")

    response = await client.post("/api/users/me/logout")

    assert response.status_code == 200
    assert response.json() == {"id": "user-viewer"}
    revoke.assert_awaited_once_with(id="user-viewer")


@pytest.mark.asyncio
async def test_logout_without_token_returns_401(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    revoke = AsyncMock()
    monkeypatch.setattr(UserTable, "revoke_sessions", revoke)

    response = await client.post("/api/users/me/logout")

    assert response.status_code == 401
    revoke.assert_not_called()


# --- 登入限流 (路由層) ----------------------------------------------------
#
# shared 的單元測試已經涵蓋 RateLimiter 本身。這裡守的是**接起來之後**才成立的事:
# LangException 帶的 Retry-After 有沒有真的通過 FastAPI 的 exception handler 變成 HTTP
# 回應標頭, 以及限流 key 是不是真的取自不可偽造的來源。


@pytest.fixture
def _clean_login_limiter():
    """限流器是 module-level 的共用狀態, 測試之間必須互不影響。"""
    from modules.users.router import login_ip_limiter, login_limiter

    login_limiter.clear()
    login_ip_limiter.clear()
    yield login_limiter
    login_limiter.clear()
    login_ip_limiter.clear()


@pytest.fixture
def _login_always_fails(monkeypatch: pytest.MonkeyPatch):
    """讓登入固定失敗, 且不碰資料庫與 bcrypt。

    限流的計數只在「沒有成功」時累積 (成功會 reset), 所以測試需要的是穩定的失敗。
    直接替換 login_user 也順便避開 bcrypt —— 真的跑十幾次雜湊會讓這個測試慢好幾秒。
    """
    from shared.http.errors import LangException

    async def always_fails(form_data, env):
        raise LangException(401, UserError.INVALID_CREDENTIALS)

    monkeypatch.setattr(account, "login_user", always_fails)


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
    # 這一行是重點: 單元測試只能證明例外物件上有這個標頭, 證明不了它會出現在回應上。
    assert "retry-after" in response.headers
    assert int(response.headers["retry-after"]) >= 1


@pytest.mark.asyncio
async def test_forged_forwarded_header_cannot_bypass_login_rate_limit(
    client: AsyncClient, _clean_login_limiter, _login_always_fails
):
    """每次換一個假的 X-Forwarded-For 也不能重新取得額度。

    限流 key 只信任 nginx 設定的 X-Real-IP, 不能受用戶端提供的 header 影響。
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


@pytest.mark.asyncio
async def test_spraying_usernames_from_one_ip_is_rate_limited(
    client: AsyncClient, _clean_login_limiter, _login_always_fails
):
    """同一個 IP 每次換一個帳號名, 也不能繞過限流。

    帳號維度的 key 是 `ip:username`, 換帳號名就是換 key —— 少了 IP 維度的那一層,
    一個來源可以對整份帳號清單各試幾次常見密碼 (password spraying) 而永遠不吃 429。
    """
    from modules.users.router import login_ip_limiter

    for i in range(login_ip_limiter.max_attempts):
        response = await client.post(
            "/api/users/login", data={"username": f"user{i}", "password": "wrong"}
        )
        assert response.status_code == 401

    response = await client.post(
        "/api/users/login", data={"username": "one-more", "password": "wrong"}
    )

    assert response.status_code == 429


# --- Session 撤銷 (auth_version) -------------------------------------------
#
# `auth_version` 讓重設密碼只撤銷目標使用者的既有 session; TOKEN_VERSION 則保留給全域撤銷。


def _token_with_auth_version(username: str, auth_version: int) -> str:
    from app.server import app
    from shared.auth.contracts import TokenSubject
    from shared.auth.tokens import create_token

    payload: TokenSubject = {"username": username, "auth_version": auth_version}
    return create_token(payload, app.state.env)["access_token"]


@pytest.mark.asyncio
async def test_token_with_stale_auth_version_is_rejected(client: AsyncClient, set_current_users):
    """重設密碼把 auth_version +1 之後, 舊 token 立刻失效。"""
    set_current_users({"super": {**USERS["super"], "auth_version": 2}})

    client.cookies.set("access_token", _token_with_auth_version("super", 1))
    response = await client.get("/api/users/me")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_token_with_current_auth_version_is_accepted(client: AsyncClient, set_current_users):
    set_current_users({"super": {**USERS["super"], "auth_version": 2}})

    client.cookies.set("access_token", _token_with_auth_version("super", 2))
    response = await client.get("/api/users/me")

    assert response.status_code == 200


# --- 改自己的密碼 -----------------------------------------------------------
#
# 與管理者的 reset_password 是兩條路徑: 這條要驗舊密碼、不需要任何 permission, 而且會把
# 一張新 token 交回來 —— 因為它撤銷的 session 包含呼叫者自己手上那一張。

_CURRENT_PASSWORD = "current-password-123"
# 真的算一次 bcrypt, 讓「舊密碼不符」那條驗到的是真正的比對, 而不是一個說不的假物件。
# 只在 module 層算這一次, 其餘測試都繞開 bcrypt (見下面的 fixture)。
_CURRENT_PASSWORD_HASH = passwords.hash_password(_CURRENT_PASSWORD)


@pytest.fixture
def _clean_password_change_limiter():
    """同 `_clean_login_limiter`: 限流器是 module-level 的共用狀態。"""
    from modules.users.router import password_change_limiter

    password_change_limiter.clear()
    yield password_change_limiter
    password_change_limiter.clear()


@pytest.fixture
def _own_password_user(monkeypatch: pytest.MonkeyPatch):
    """viewer 這個帳號: 舊密碼是真的 hash, 寫入與新密碼的雜湊則換成假的。

    只留「比對舊密碼」是真的 —— 那是這幾條測試唯一要驗的行為, 其餘都是別處已經測過的。
    """
    monkeypatch.setattr(
        UserTable,
        "find_detail_by_username",
        AsyncMock(
            return_value={
                **USERS["viewer"],
                "username": "viewer",
                "auth_version": 1,
                "password": _CURRENT_PASSWORD_HASH,
            }
        ),
    )
    monkeypatch.setattr(
        UserTable,
        "set_password_and_revoke_sessions",
        AsyncMock(return_value={"id": USERS["viewer"]["id"], "auth_version": 2}),
    )
    monkeypatch.setattr(passwords, "hash_password_async", AsyncMock(return_value="hashed"))


@pytest.mark.asyncio
async def test_change_own_password_without_token_returns_401(client: AsyncClient):
    response = await client.patch(
        "/api/users/me/password",
        json={"current_password": _CURRENT_PASSWORD, "new_password": "new-password-123"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_change_own_password_returns_a_token_with_the_new_auth_version(
    client: AsyncClient, _own_password_user, _clean_password_change_limiter
):
    """**這條是這個端點存在的形狀**: 換完密碼要拿得到一張還能用的 token。

    少了它, 使用者按下「更新密碼」之後的下一個動作就是被踢回登入頁 —— 而畫面上剛剛才說
    成功。新 token 的世代必須是資料庫回來的那個 (2), 不是呼叫端手上的舊值。
    """
    from app.server import app
    from shared.auth.tokens import parse_token

    authenticate(client, "viewer")

    response = await client.patch(
        "/api/users/me/password",
        json={"current_password": _CURRENT_PASSWORD, "new_password": "new-password-123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert parse_token(body["access_token"], app.state.env) == {
        "username": "viewer",
        "auth_version": 2,
    }


@pytest.mark.asyncio
async def test_wrong_current_password_returns_403_not_401(
    client: AsyncClient, _own_password_user, _clean_password_change_limiter
):
    """**401 在這裡是錯的答案, 所以要明確斷言它不是。**

    前端的 `shared/api/request.server.ts` 把 401 一律解釋成 session 過期: 刪掉 cookie、
    導向 `/login?reason=session-expired`。回 401 等於「舊密碼打錯一個字就被登出」,
    而使用者完全看不出發生了什麼事。
    """
    authenticate(client, "viewer")

    response = await client.patch(
        "/api/users/me/password",
        json={"current_password": "not-the-password", "new_password": "new-password-123"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_new_password_must_meet_the_strength_rule(
    client: AsyncClient, _own_password_user, _clean_password_change_limiter
):
    """強度規則只套在**新**密碼上。

    舊密碼刻意只要求非空 (見 schema.PasswordChange) —— 它可能是規則變嚴之前設的,
    拿新規則擋它會讓最該換密碼的那批人反而換不了。
    """
    authenticate(client, "viewer")

    response = await client.patch(
        "/api/users/me/password",
        json={"current_password": _CURRENT_PASSWORD, "new_password": "short"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_change_own_password_is_rate_limited_per_user(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    _own_password_user,
    _clean_password_change_limiter,
):
    """限流的 key 是認證後的使用者 id, 換 IP 躲不掉。

    擋的主要不是猜密碼 (能打到這裡的人已經有有效 session), 是每次呼叫都要算的那把
    bcrypt —— 不限流的話一個被盜的 session 就是一台現成的 CPU 消耗器。
    """
    # 這條測的是限流, 不是雜湊: 換掉比對函式省下十幾次 bcrypt。
    monkeypatch.setattr(passwords, "verify_password_async", AsyncMock(return_value=False))
    limiter = _clean_password_change_limiter
    authenticate(client, "viewer")
    payload = {"current_password": "wrong", "new_password": "new-password-123"}

    for i in range(limiter.max_attempts):
        response = await client.patch(
            "/api/users/me/password",
            json=payload,
            headers={"X-Real-IP": f"1.2.3.{i}"},
        )
        assert response.status_code == 403

    response = await client.patch(
        "/api/users/me/password",
        json=payload,
        headers={"X-Real-IP": "9.9.9.9"},
    )

    assert response.status_code == 429
    assert int(response.headers["retry-after"]) >= 1
