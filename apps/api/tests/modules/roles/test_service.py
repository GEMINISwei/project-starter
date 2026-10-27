"""角色的操作 (`modules/roles/service.py`): 系統角色的保護、一般角色不能持有萬用字元與寫入的欄位。

資料表方法以 monkeypatch 換掉, 被測的是 service 自己的判斷。路由層在 `test_routes.py`。
"""

from typing import Any

import pytest

from app.permissions import Permission
from modules.roles import service as role_service
from modules.roles.model import RoleTable
from modules.roles.schema import RoleCreate, RoleUpdate
from modules.roles.service import RoleError
from shared.http.errors import LangException

SYSTEM_ROLE = {
    "id": "role-super",
    "code": "super_admin",
    "name": "超級管理者",
    "permissions": [Permission.ALL],
    "is_disabled": False,
}

REGULAR_ROLE: dict[str, Any] = {
    "id": "role-reader",
    "code": None,
    "name": "一般",
    "permissions": [],
    "is_disabled": False,
}


@pytest.fixture
def roles(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """幾個角色查得到; 回傳 `create`/`update_by_id` 收到的資料。"""
    stored = {role["id"]: role for role in (SYSTEM_ROLE, REGULAR_ROLE)}
    writes: list[dict[str, Any]] = []

    async def fake_find(id, session=None):
        return stored.get(id)

    async def fake_update(id, data=None, session=None, *, also_changed=False):
        writes.append({"id": id, **(data or {})})
        return {"id": id}

    async def fake_create(data, session=None):
        writes.append(data)
        return {"id": "role-new"}

    monkeypatch.setattr(RoleTable, "find_detail_by_id", fake_find)
    monkeypatch.setattr(RoleTable, "update_by_id", fake_update)
    monkeypatch.setattr(RoleTable, "create", fake_create)
    return writes


async def _expect_error(call, status: int, error: RoleError) -> None:
    with pytest.raises(LangException) as exc_info:
        await call
    assert exc_info.value.status_code == status
    assert exc_info.value.detail == error.value.zh


def _create(permissions: list[Permission], name: str = "編輯"):
    return role_service.create_role(form_data=RoleCreate(name=name, permissions=permissions))


def _update(
    role_id: str,
    *,
    name: str,
    permissions: list[Permission],
    is_disabled: bool = False,
):
    return role_service.update_role(
        id=role_id,
        form_data=RoleUpdate(name=name, permissions=permissions, is_disabled=is_disabled),
    )


def _disable(role_id: str):
    return role_service.disable_role(id=role_id)


# ── 一般角色不能持有萬用字元 ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_role_writes_exactly_the_listed_fields(roles):
    """逐欄寫入, 而且建出來的一律是一般角色 (`code` 是 None)。"""
    await _create([])

    assert roles == [{"name": "編輯", "permissions": [], "code": None}]


@pytest.mark.asyncio
async def test_create_role_with_wildcard_is_rejected(roles):
    await _expect_error(
        _create([Permission.ALL], name="偽超管"),
        403,
        RoleError.CANNOT_USE_ALL_PERMISSION,
    )
    assert roles == []


# ── 一般角色的修改與停用 ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_regular_role_writes_permissions_and_status(roles):
    await _update("role-reader", name="一般", permissions=[], is_disabled=True)

    assert roles[0]["permissions"] == []
    assert roles[0]["is_disabled"] is True


@pytest.mark.asyncio
async def test_update_regular_role_to_wildcard_is_rejected(roles):
    await _expect_error(
        _update("role-reader", name="一般", permissions=[Permission.ALL]),
        403,
        RoleError.CANNOT_USE_ALL_PERMISSION,
    )
    assert roles == []


@pytest.mark.asyncio
async def test_disable_regular_role(roles):
    await _disable("role-reader")

    assert roles[0]["is_disabled"] is True


@pytest.mark.asyncio
async def test_disable_missing_role_returns_404(roles):
    await _expect_error(_disable("role-missing"), 404, RoleError.NOT_FOUND)


# ── 系統角色 (code 不為 None) 的保護 ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_system_role_permissions_are_immutable(roles):
    await _expect_error(
        _update("role-super", name="超級管理者", permissions=[]),
        403,
        RoleError.CANNOT_UPDATE_DEFAULT_PERMISSIONS,
    )
    assert roles == []


@pytest.mark.asyncio
async def test_system_role_cannot_be_disabled_by_update(roles):
    await _expect_error(
        # 權限維持不變, 只想停用 —— 一樣要被擋。
        _update("role-super", name="超級管理者", permissions=[Permission.ALL], is_disabled=True),
        403,
        RoleError.CANNOT_DISABLE_DEFAULT,
    )


@pytest.mark.asyncio
async def test_system_role_cannot_be_disabled_by_delete(roles):
    await _expect_error(_disable("role-super"), 403, RoleError.CANNOT_DISABLE_DEFAULT)


@pytest.mark.asyncio
async def test_system_role_cannot_be_renamed(roles):
    """名稱跟權限一樣由 seed 同步: 放行改名的話, 下次部署後會被悄悄改回來。"""
    await _expect_error(
        _update("role-super", name="最高管理者", permissions=[Permission.ALL]),
        403,
        RoleError.CANNOT_RENAME_DEFAULT,
    )
    assert roles == []


@pytest.mark.asyncio
async def test_system_role_update_without_changes_is_accepted(roles):
    """原樣送回 (名稱、權限、狀態都不變) 不算違規, 交給 `update_by_id` 判斷成無變更。"""
    await _update("role-super", name="超級管理者", permissions=[Permission.ALL])

    assert roles == [{"id": "role-super", "name": "超級管理者"}]
