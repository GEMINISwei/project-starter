"""使用者對自己帳號的操作 (`modules/users/account.py`): 登入。

改自己密碼的路徑在 `test_routes.py` (連同限流與新 token 一起驗)。這裡補的是登入本身:
路由測試為了避開 bcrypt 會把 `login_user` 整個換掉, 所以「停用的帳號不能登入」這類規則
只有在這裡才真的被執行到。
"""

import pytest

from modules.users import account
from modules.users.errors import UserError
from modules.users.model import UserTable
from modules.users.schema import UserLogin
from shared.auth import passwords
from shared.auth.tokens import parse_token
from shared.http.errors import LangException
from tests.shared.minimal_app import MinimalEnv

ENV = MinimalEnv()
PASSWORD = "correct-password"
# 真的算一次 bcrypt, 讓比對走的是真正的雜湊; 只在 module 層算這一次。
PASSWORD_HASH = passwords.hash_password(PASSWORD)


@pytest.fixture
def stored_user(monkeypatch: pytest.MonkeyPatch):
    """`viewer` 這個帳號的資料; 回傳 dict 讓各測試改欄位 (例如停用)。"""
    user = {
        "id": "user-1",
        "username": "viewer",
        "auth_version": 3,
        "permissions": [],
        "is_disabled": False,
        "password": PASSWORD_HASH,
    }

    async def fake_find(username, include_password=False, session=None):
        return user if username == "viewer" else None

    monkeypatch.setattr(UserTable, "find_detail_by_username", fake_find)
    return user


async def _expect_invalid_credentials(username: str, password: str) -> None:
    with pytest.raises(LangException) as exc_info:
        await account.login_user(UserLogin(username=username, password=password), ENV)
    assert exc_info.value.status_code == 401
    # 三種失敗回同一個訊息: 分開說的話, 錯誤訊息本身就能拿來窮舉帳號。
    assert exc_info.value.detail == UserError.INVALID_CREDENTIALS.value.zh


@pytest.mark.asyncio
async def test_login_with_correct_password_returns_a_token_for_that_user(stored_user):
    token = await account.login_user(UserLogin(username="viewer", password=PASSWORD), ENV)

    payload = parse_token(token.access_token, ENV)
    assert payload["username"] == "viewer"
    # token 帶的世代要是資料庫裡的那一個, 否則換過密碼的人一登入就被當成舊憑證。
    assert payload["auth_version"] == 3


@pytest.mark.asyncio
async def test_login_with_wrong_password_is_rejected(stored_user):
    await _expect_invalid_credentials("viewer", "wrong-password")


@pytest.mark.asyncio
async def test_login_to_disabled_account_is_rejected_even_with_correct_password(stored_user):
    stored_user["is_disabled"] = True

    await _expect_invalid_credentials("viewer", PASSWORD)


@pytest.mark.asyncio
async def test_login_to_unknown_account_still_runs_the_password_check(
    stored_user, monkeypatch: pytest.MonkeyPatch
):
    """帳號不存在時也要走完一次比對, 這裡確認有呼叫到。

    時間差防護本身 (比對 dummy hash) 在 `shared/auth/passwords.py`, 那裡另有測試。
    """
    checked: list[str | None] = []
    real_check = passwords.verify_login_password

    async def recording_check(plain_password: str, hashed_password: str | None) -> bool:
        checked.append(hashed_password)
        return await real_check(plain_password, hashed_password)

    monkeypatch.setattr(passwords, "verify_login_password", recording_check)

    await _expect_invalid_credentials("nobody", PASSWORD)
    assert checked == [None]
