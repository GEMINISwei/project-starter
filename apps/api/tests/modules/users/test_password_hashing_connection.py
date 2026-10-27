"""跑 bcrypt 的時候不持有資料庫交易, 以及自己改密碼遇到併發變更時回 409。

bcrypt 一次 100–300ms, 期間佔著連線的話, 大量登入 (例如全員撤銷之後) 會把連線池佔滿,
連帶讓所有其他請求拿不到連線。要真的 PostgreSQL 才看得到連線有沒有還回連線池。

`db` fixture 本身就是一個請求的 session, 跟 middleware 開的一樣。
"""

from collections.abc import Callable

import pytest
from sqlalchemy import select

from modules.users import account, service
from modules.users.model import UserTable
from modules.users.schema import PasswordChange, UserLogin, UserResetPassword
from shared.auth import passwords
from shared.db.session import active_session, session_scope
from shared.http.errors import LangException
from tests.shared.db.test_session import checked_out_connections
from tests.shared.minimal_app import MinimalEnv

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

ENV = MinimalEnv()
PASSWORD = "correct-password"
PASSWORD_HASH = passwords.hash_password(PASSWORD)


async def _create_user(username: str) -> str:
    """建好使用者並 commit: 寫入要在「請求」開始之前就結束, 否則請求本身就算寫過資料。"""
    session = active_session()
    user = UserTable(username=username, password=PASSWORD_HASH, nickname=username)
    session.add(user)
    await session.flush()
    await session.commit()
    return str(user.id)


def _watch(monkeypatch: pytest.MonkeyPatch, name: str, seen: list[tuple[bool, int]]) -> None:
    """把 `passwords.<name>` 包一層, 記下被呼叫當下有沒有交易、借出幾條連線。"""
    original: Callable = getattr(passwords, name)

    async def watched(*args, **kwargs):
        session = active_session()
        seen.append((session.in_transaction(), checked_out_connections(session)))
        return await original(*args, **kwargs)

    monkeypatch.setattr(passwords, name, watched)


async def test_login_releases_connection_during_password_check(db, monkeypatch):
    await _create_user("viewer")
    seen: list[tuple[bool, int]] = []
    _watch(monkeypatch, "verify_login_password", seen)

    await account.login_user(UserLogin(username="viewer", password=PASSWORD), ENV)

    assert seen == [(False, 0)]


async def test_change_own_password_releases_connection_during_hashing(db, monkeypatch):
    await _create_user("viewer")
    current_user = await UserTable.find_detail_by_username("viewer")
    assert current_user is not None
    seen: list[tuple[bool, int]] = []
    _watch(monkeypatch, "verify_password_async", seen)
    _watch(monkeypatch, "hash_password_async", seen)

    await account.change_own_password(
        current_user=current_user,
        form_data=PasswordChange(current_password=PASSWORD, new_password="new-password-123"),
        env=ENV,
    )

    assert seen == [(False, 0), (False, 0)]


async def test_reset_user_password_releases_connection_during_hashing(db, monkeypatch):
    user_id = await _create_user("viewer")
    seen: list[tuple[bool, int]] = []
    _watch(monkeypatch, "hash_password_async", seen)

    await service.reset_user_password(
        id=user_id, form_data=UserResetPassword(password="new-password-123")
    )

    assert seen == [(False, 0)]


async def test_change_own_password_concurrent_change_returns_409(db, monkeypatch):
    """bcrypt 期間另一個請求換了密碼或登出 (auth_version 變了): 不能用舊的比對結果覆寫。"""
    user_id = await _create_user("viewer")
    current_user = await UserTable.find_detail_by_username("viewer")
    assert current_user is not None
    original_hash = passwords.hash_password_async

    async def hash_while_another_request_logs_out(raw_password: str) -> str:
        async with session_scope():
            await UserTable.revoke_sessions(id=user_id)
        return await original_hash(raw_password)

    monkeypatch.setattr(passwords, "hash_password_async", hash_while_another_request_logs_out)

    with pytest.raises(LangException) as exc_info:
        await account.change_own_password(
            current_user=current_user,
            form_data=PasswordChange(current_password=PASSWORD, new_password="new-password-123"),
            env=ENV,
        )

    assert exc_info.value.status_code == 409
    await active_session().rollback()
    stored = (
        await active_session().execute(
            select(UserTable.password, UserTable.auth_version).where(UserTable.username == "viewer")
        )
    ).one()
    # 密碼沒被覆寫, 世代號只有另一個請求加的那一次。
    assert stored.password == PASSWORD_HASH
    assert stored.auth_version == 2
