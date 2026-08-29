"""Service 層的授權規則測試。

這些規則決定「誰能對誰做什麼」，屬於不需要資料庫的純邏輯。此處只 stub Document
查詢，被測的是 Service 自己的判斷。
"""

import pytest

from app.permissions import Permission, build_permission_catalog
from app.registry import ENABLED_MODULES
from modules.roles import service as role_service
from modules.roles.model import RoleTable
from modules.roles.schema import RoleUpdate
from modules.roles.service import RoleError
from modules.users import service as user_service
from modules.users.model import UserDetail, UserTable
from modules.users.service import UserError
from shared.auth.contracts import CurrentUser
from shared.http.errors import LangException

# service 收 resolver 當參數（不再 import 全域），所以測試自己組一份完整目錄的 resolver，
# 等同 `create_app()` 掛到 `app.state.permission_resolver` 的那一個。
RESOLVER = build_permission_catalog(
    spec for module in ENABLED_MODULES for spec in module.permissions
).resolver


def _target(user_id: str, permissions: list[str] | None = None) -> UserDetail:
    """被操作的對象：從 DB 查出的使用者文件，形狀比 CurrentUser 寬（帶 disabled_at）。"""
    return {
        "id": user_id,
        "username": user_id,
        "nickname": user_id,
        "role_ids": [],
        "permissions": permissions or [],
        "is_disabled": False,
        "disabled_at": None,
    }


def _user(user_id: str, permissions: list[str] | None = None) -> CurrentUser:
    return {
        "id": user_id,
        "username": user_id,
        "nickname": user_id,
        "auth_version": 1,
        "permissions": permissions or [],
        "is_disabled": False,
    }


def _role(role_id: str, permissions: list[str], *, is_disabled: bool = False) -> dict:
    return {"id": role_id, "permissions": permissions, "is_disabled": is_disabled}


# ── 停用使用者的保護 ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cannot_disable_self():
    """不能停用自己 —— 否則管理員可以把自己鎖在系統外。"""
    me = _user("user-1", [Permission.USER_MANAGE])

    with pytest.raises(LangException) as exc_info:
        await user_service._apply_disable_user(
            current_user=me, target=_target("user-1"), resolver=RESOLVER
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == UserError.CANNOT_DISABLE_SELF.value.zh


@pytest.mark.asyncio
async def test_cannot_disable_super_admin():
    """不能停用超級管理者，即使自己也有管理權限。"""
    me = _user("user-1", [Permission.USER_MANAGE])
    super_admin = _target("user-2", [Permission.ALL])

    with pytest.raises(LangException) as exc_info:
        await user_service._apply_disable_user(
            current_user=me, target=super_admin, resolver=RESOLVER
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == UserError.CANNOT_DISABLE_SUPER.value.zh


@pytest.mark.asyncio
async def test_can_disable_regular_user(monkeypatch):
    """相對的：停用一般使用者要能成功，避免上面兩條規則寫得過嚴。"""
    captured = {}

    async def fake_update(id, data=None, session=None):
        captured["id"] = id
        captured["data"] = data
        return {"id": id}

    monkeypatch.setattr(UserTable, "update_by_id", fake_update)

    await user_service._apply_disable_user(
        current_user=_user("admin", [Permission.USER_MANAGE]),
        target=_target("victim", [Permission.USER_READ]),
        resolver=RESOLVER,
    )

    assert captured["id"] == "victim"
    assert captured["data"]["is_disabled"] is True
    assert captured["data"]["disabled_at"] is not None


# ── 指派角色的保護 ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cannot_assign_super_admin_role(monkeypatch):
    """一般路徑不得指派帶有 `*` 的角色 —— 這是最直接的提權路徑。"""

    async def fake_find(ids):
        return [_role("role-super", [Permission.ALL])]

    monkeypatch.setattr(RoleTable, "find_details_by_ids", fake_find)

    with pytest.raises(LangException) as exc_info:
        await user_service.validate_role_ids(role_ids=["role-super"])

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == UserError.CANNOT_ASSIGN_SUPER_ADMIN.value.zh


@pytest.mark.asyncio
async def test_validate_role_ids_has_no_super_admin_escape_hatch(monkeypatch):
    """`validate_role_ids` **無條件**拒絕帶 Permission.ALL 的角色，沒有例外參數。

    這個測試同時釘住「呼叫端無法把它繞開」：多傳一個參數會是 TypeError，
    而不是悄悄地放行。
    """
    import inspect

    async def fake_find(ids):
        return [_role("role-super", [Permission.ALL])]

    monkeypatch.setattr(RoleTable, "find_details_by_ids", fake_find)

    with pytest.raises(LangException) as exc_info:
        await user_service.validate_role_ids(role_ids=["role-super"])
    assert exc_info.value.status_code == 403

    # 簽名上不該再有任何「放行」用的參數。
    params = set(inspect.signature(user_service.validate_role_ids).parameters)
    assert params == {"role_ids"}


@pytest.mark.asyncio
async def test_cannot_assign_disabled_role(monkeypatch):
    async def fake_find(ids):
        return [_role("role-1", [Permission.USER_READ], is_disabled=True)]

    monkeypatch.setattr(RoleTable, "find_details_by_ids", fake_find)

    with pytest.raises(LangException) as exc_info:
        await user_service.validate_role_ids(role_ids=["role-1"])

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == UserError.ROLE_DISABLED.value.zh


@pytest.mark.asyncio
async def test_unknown_role_id_is_rejected(monkeypatch):
    """要求兩個角色但只查到一個時要擋下來，不能默默只套用查到的那個。"""

    async def fake_find(ids):
        return [_role("role-1", [Permission.USER_READ])]

    monkeypatch.setattr(RoleTable, "find_details_by_ids", fake_find)

    with pytest.raises(LangException) as exc_info:
        await user_service.validate_role_ids(role_ids=["role-1", "role-missing"])

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == UserError.ROLE_NOT_FOUND.value.zh


# ── 角色本身的保護 ──────────────────────────────────────────────────────────────


def test_regular_role_cannot_hold_wildcard_permission():
    with pytest.raises(LangException) as exc_info:
        role_service.validate_regular_permissions([Permission.USER_READ, Permission.ALL])

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == RoleError.CANNOT_USE_ALL_PERMISSION.value.zh


def test_regular_role_accepts_normal_permissions():
    role_service.validate_regular_permissions([Permission.USER_READ, Permission.ROLE_READ])


@pytest.mark.asyncio
async def test_system_role_permissions_are_immutable(monkeypatch):
    """系統角色（code 不為 None）的權限不可被改動。"""
    system_role = {
        "id": "role-super",
        "code": "super_admin",
        "name": "超級管理者",
        "permissions": [Permission.ALL],
        "is_disabled": False,
    }

    async def fake_find_detail(id):
        return system_role

    monkeypatch.setattr(RoleTable, "find_detail_by_id", fake_find_detail)

    with pytest.raises(LangException) as exc_info:
        await role_service.update_role(
            "role-super",
            RoleUpdate(name="改名", permissions=[Permission.USER_READ], is_disabled=False),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == RoleError.CANNOT_UPDATE_DEFAULT_PERMISSIONS.value.zh


@pytest.mark.asyncio
async def test_system_role_cannot_be_disabled(monkeypatch):
    system_role = {
        "id": "role-super",
        "code": "super_admin",
        "name": "超級管理者",
        "permissions": [Permission.ALL],
        "is_disabled": False,
    }

    async def fake_find_detail(id):
        return system_role

    monkeypatch.setattr(RoleTable, "find_detail_by_id", fake_find_detail)

    with pytest.raises(LangException) as exc_info:
        await role_service.update_role(
            "role-super",
            # 權限維持不變，只想停用 —— 一樣要被擋。
            RoleUpdate(name="超級管理者", permissions=[Permission.ALL], is_disabled=True),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == RoleError.CANNOT_DISABLE_DEFAULT.value.zh
