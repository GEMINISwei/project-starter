"""超級管理者對任意使用者的操作 (`modules/users/service.py`): 保護規則與寫入的欄位。

「誰能呼叫」由路由層的 `Permission.ALL` 決定 (在 `test_routes.py`); 這裡測的是即使操作者是
超級管理者也不能做的事。資料表方法以 monkeypatch 換掉, 被測的是 service 自己的判斷。

**一律從公開函式進入** (`disable_user`、`update_user`), 不測私有的輔助函式:
停用有兩個入口, 規則必須在兩邊都成立, 只測輔助函式證明不了這件事。
"""

from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app.permissions import Permission
from modules.roles.public import RoleTable
from modules.users import service as user_service
from modules.users.errors import UserError
from modules.users.model import UserDetail, UserTable
from modules.users.schema import UserCreate, UserResetPassword, UserUpdate
from shared.auth import passwords
from shared.auth.contracts import CurrentUser
from shared.http.errors import LangException

ROLE_ID = "00000000-0000-0000-0000-0000000000a1"


def _target(user_id: str, permissions: list[str] | None = None) -> UserDetail:
    """被操作的對象: 從 DB 查出的使用者文件, 形狀與 CurrentUser 不同 (帶 nickname、role_ids)。"""
    return {
        "id": user_id,
        "username": user_id,
        "nickname": user_id,
        "role_ids": [],
        "permissions": permissions or [],
        "is_disabled": False,
    }


def _user(user_id: str, permissions: list[str] | None = None) -> CurrentUser:
    return {
        "id": user_id,
        "username": user_id,
        "auth_version": 1,
        "permissions": permissions or [],
        "is_disabled": False,
    }


def _role(role_id: str, permissions: list[str], *, is_disabled: bool = False) -> dict:
    return {"id": role_id, "permissions": permissions, "is_disabled": is_disabled}


SUPER = _user("root", [Permission.ALL])


@pytest.fixture
def users(monkeypatch: pytest.MonkeyPatch):
    """以 id 查得到的使用者, 加上記錄 `update_by_id` 寫了什麼。"""
    stored: dict[str, UserDetail] = {}
    writes: list[dict[str, Any]] = []

    async def fake_find(id, session=None):
        return stored.get(id)

    async def fake_update(id, data=None, session=None, *, also_changed=False):
        writes.append({"id": id, **(data or {})})
        return {"id": id}

    monkeypatch.setattr(UserTable, "find_detail_by_id", fake_find)
    monkeypatch.setattr(UserTable, "update_by_id", fake_update)

    def add(user: UserDetail) -> None:
        stored[user["id"]] = user

    add.writes = writes  # type: ignore[attr-defined]
    return add


@pytest.fixture
def assignable_role(monkeypatch: pytest.MonkeyPatch):
    async def fake_find(ids):
        return [_role(ROLE_ID, [])]

    monkeypatch.setattr(RoleTable, "find_details_by_ids", fake_find)


async def _expect_error(call, status: int, error: UserError) -> None:
    with pytest.raises(LangException) as exc_info:
        await call
    assert exc_info.value.status_code == status
    assert exc_info.value.detail == error.value.zh


# ── 停用: DELETE 與 PATCH 兩個入口要套同一組規則 ─────────────────────────────


@pytest.mark.asyncio
async def test_disable_user_rejects_self(users):
    """不能停用自己 —— 否則管理員可以把自己鎖在系統外。"""
    users(_target("user-1"))

    await _expect_error(
        user_service.disable_user(
            current_user=_user("user-1", [Permission.ALL]), target_id="user-1"
        ),
        403,
        UserError.CANNOT_DISABLE_SELF,
    )


@pytest.mark.asyncio
async def test_disable_user_rejects_super_admin(users):
    """不能停用超級管理者, 即使自己也是超級管理者。"""
    users(_target("user-2", [Permission.ALL]))

    await _expect_error(
        user_service.disable_user(current_user=SUPER, target_id="user-2"),
        403,
        UserError.CANNOT_DISABLE_SUPER,
    )


@pytest.mark.asyncio
async def test_disable_user_disables_a_regular_user(users):
    """相對的: 停用一般使用者要能成功, 避免上面兩條規則寫得過嚴。"""
    users(_target("victim"))

    await user_service.disable_user(current_user=SUPER, target_id="victim")

    assert users.writes[0]["id"] == "victim"
    assert users.writes[0]["is_disabled"] is True


@pytest.mark.asyncio
async def test_patch_cannot_disable_self(users):
    users(_target("user-1"))

    await _expect_error(
        user_service.update_user(
            current_user=_user("user-1", [Permission.ALL]),
            id="user-1",
            form_data=UserUpdate(nickname="me", is_disabled=True),
        ),
        403,
        UserError.CANNOT_DISABLE_SELF,
    )
    assert users.writes == []


@pytest.mark.asyncio
async def test_patch_cannot_disable_super_admin(users):
    users(_target("user-2", [Permission.ALL]))

    await _expect_error(
        user_service.update_user(
            current_user=SUPER,
            id="user-2",
            form_data=UserUpdate(nickname="super", is_disabled=True),
        ),
        403,
        UserError.CANNOT_DISABLE_SUPER,
    )
    assert users.writes == []


# ── 修改資料 ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_user_can_reenable_and_assign_roles(users, assignable_role):
    users({**_target("user-2"), "is_disabled": True})

    await user_service.update_user(
        current_user=SUPER,
        id="user-2",
        form_data=UserUpdate(nickname="n", is_disabled=False, role_ids=[ROLE_ID]),
    )

    assert users.writes == [
        {
            "id": "user-2",
            "nickname": "n",
            "role_ids": [ROLE_ID],
            "is_disabled": False,
        }
    ]


@pytest.mark.asyncio
async def test_update_user_with_empty_role_ids_clears_roles(users, monkeypatch):
    """`role_ids=[]` 是「改成未指派」, 不是「不改」(不改是不帶這個欄位)。"""
    users(_target("user-2"))

    async def fake_find(ids):
        return []

    monkeypatch.setattr(RoleTable, "find_details_by_ids", fake_find)

    await user_service.update_user(
        current_user=SUPER,
        id="user-2",
        form_data=UserUpdate(nickname="n", is_disabled=False, role_ids=[]),
    )

    assert users.writes[0]["role_ids"] == []


@pytest.mark.asyncio
async def test_cannot_change_super_admin_roles(users, assignable_role):
    """拿掉超管的角色等於把他降級; 理由同不能重設超管的密碼。"""
    users(_target("root-2", [Permission.ALL]))

    await _expect_error(
        user_service.update_user(
            current_user=SUPER,
            id="root-2",
            form_data=UserUpdate(nickname="n", is_disabled=False, role_ids=[]),
        ),
        403,
        UserError.CANNOT_CHANGE_SUPER_ROLES,
    )
    assert users.writes == []


@pytest.mark.asyncio
async def test_super_admin_nickname_can_still_be_edited(users):
    users(_target("root-2", [Permission.ALL]))

    await user_service.update_user(
        current_user=SUPER,
        id="root-2",
        form_data=UserUpdate(nickname="n", is_disabled=False),
    )

    assert users.writes == [{"id": "root-2", "nickname": "n", "is_disabled": False}]


# ── 建立使用者 ────────────────────────────────────────────────────────────────


@pytest.fixture
def created(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """記錄 `UserTable.create` 收到的資料; 帳號一律不存在, 雜湊換成固定值省下 bcrypt。"""
    received: list[dict] = []

    async def fake_create(data, session=None):
        received.append(data)
        return {"id": "new-user"}

    async def no_user(username, include_password=False, session=None):
        return None

    async def fake_hash(raw_password):
        return f"hashed:{raw_password}"

    monkeypatch.setattr(UserTable, "create", fake_create)
    monkeypatch.setattr(UserTable, "find_detail_by_username", no_user)
    monkeypatch.setattr(passwords, "hash_password_async", fake_hash)
    return received


@pytest.mark.asyncio
async def test_create_user_writes_exactly_the_listed_fields(created, assignable_role):
    """逐欄寫入: 密碼只以雜湊落地, 表單沒有的欄位不會出現。"""
    await user_service.create_user(
        UserCreate(username="new", password="password-123", nickname="新人", role_ids=[ROLE_ID]),
    )

    assert created == [
        {
            "username": "new",
            "nickname": "新人",
            "password": "hashed:password-123",
            "role_ids": [ROLE_ID],
        }
    ]


@pytest.mark.asyncio
async def test_create_user_with_existing_username_returns_409(monkeypatch, created):
    async def existing(username, include_password=False, session=None):
        return _user(username)

    monkeypatch.setattr(UserTable, "find_detail_by_username", existing)

    await _expect_error(
        user_service.create_user(
            UserCreate(username="taken", password="password-123", nickname="n"),
        ),
        409,
        UserError.USERNAME_EXISTS,
    )
    assert created == []


@pytest.mark.asyncio
async def test_create_user_racing_on_username_returns_409(monkeypatch, created):
    """查詢時還不存在、寫入時撞到唯一約束 (併發) —— 要回 409, 不是 500。"""

    class _UniqueViolationError(Exception):
        sqlstate = "23505"

    async def racing_create(data, session=None):
        raise IntegrityError("INSERT", {}, _UniqueViolationError())

    monkeypatch.setattr(UserTable, "create", racing_create)

    await _expect_error(
        user_service.create_user(
            UserCreate(username="race", password="password-123", nickname="n"),
        ),
        409,
        UserError.USERNAME_EXISTS,
    )


# ── 指派角色的保護 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cannot_assign_super_admin_role(monkeypatch):
    """一般路徑不得指派帶有 `*` 的角色 —— 這是最直接的提權路徑。"""

    async def fake_find(ids):
        return [_role("role-super", [Permission.ALL])]

    monkeypatch.setattr(RoleTable, "find_details_by_ids", fake_find)

    await _expect_error(
        user_service.validate_role_ids(["role-super"]),
        403,
        UserError.CANNOT_ASSIGN_SUPER_ADMIN,
    )


@pytest.mark.asyncio
async def test_cannot_assign_disabled_role(monkeypatch):
    async def fake_find(ids):
        return [_role("role-1", [], is_disabled=True)]

    monkeypatch.setattr(RoleTable, "find_details_by_ids", fake_find)

    await _expect_error(
        user_service.validate_role_ids(["role-1"]),
        400,
        UserError.ROLE_DISABLED,
    )


@pytest.mark.asyncio
async def test_unknown_role_id_is_rejected(monkeypatch):
    """要求兩個角色但只查到一個時要擋下來, 不能默默只套用查到的那個。"""

    async def fake_find(ids):
        return [_role("role-1", [])]

    monkeypatch.setattr(RoleTable, "find_details_by_ids", fake_find)

    await _expect_error(
        user_service.validate_role_ids(["role-1", "role-missing"]),
        404,
        UserError.ROLE_NOT_FOUND,
    )


# ── 重設密碼 ────────────────────────────────────────────────────────────────


@pytest.fixture
def password_writes(monkeypatch: pytest.MonkeyPatch, users) -> list[str]:
    """記錄被重設密碼的 id; 雜湊換成固定值省下 bcrypt。"""
    written: list[str] = []

    async def fake_set(id, password_hash, session=None):
        written.append(id)
        return {"id": id, "auth_version": 2}

    async def fake_hash(raw_password):
        return f"hashed:{raw_password}"

    monkeypatch.setattr(UserTable, "set_password_and_revoke_sessions", fake_set)
    monkeypatch.setattr(passwords, "hash_password_async", fake_hash)
    return written


@pytest.mark.asyncio
async def test_cannot_reset_super_admin_password(users, password_writes):
    """超管不能重設另一位超管的密碼, 否則一位超管可以把其他超管鎖在系統外。"""
    users(_target("root-2", [Permission.ALL]))

    await _expect_error(
        user_service.reset_user_password(
            id="root-2", form_data=UserResetPassword(password="new-password-123")
        ),
        403,
        UserError.CANNOT_RESET_SUPER_PASSWORD,
    )
    assert password_writes == []


@pytest.mark.asyncio
async def test_cannot_reset_own_password_from_admin(users, password_writes):
    """自己也是超管 —— 改自己的密碼走 `/users/me/password` (要驗舊密碼, 也不會被登出)。"""
    users(_target("root", [Permission.ALL]))

    await _expect_error(
        user_service.reset_user_password(
            id="root", form_data=UserResetPassword(password="new-password-123")
        ),
        403,
        UserError.CANNOT_RESET_SUPER_PASSWORD,
    )
    assert password_writes == []


@pytest.mark.asyncio
async def test_reset_regular_user_password(users, password_writes):
    users(_target("user-2"))

    await user_service.reset_user_password(
        id="user-2", form_data=UserResetPassword(password="new-password-123")
    )

    assert password_writes == ["user-2"]
