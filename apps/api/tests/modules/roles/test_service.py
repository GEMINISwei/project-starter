"""角色的操作 (`modules/roles/service.py`): 系統角色的保護、一般角色不能持有萬用字元與寫入的欄位。

資料表方法以 monkeypatch 換掉, 被測的是 service 自己的判斷。路由層在 `test_routes.py`。
"""

from typing import Any

import pytest
from sqlalchemy.exc import IntegrityError

from app.permissions import Permission
from modules.roles import service as role_service
from modules.roles.model import RoleTable
from modules.roles.schema import RoleCreate, RoleUpdate
from modules.roles.service import RoleError
from shared.http.errors import LangException
from tests.audit import acting_as, events

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

    async def fake_find_by_name(name, session=None):
        return next((role for role in stored.values() if role["name"] == name), None)

    monkeypatch.setattr(RoleTable, "find_detail_by_id", fake_find)
    monkeypatch.setattr(RoleTable, "find_detail_by_name", fake_find_by_name)
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


# ── 角色名稱不可重複 ─────────────────────────────────────────────────────────
#
# 指派角色時畫面上只看得到名稱, 同名的兩個角色會讓管理者分不清、把權限給錯人。


@pytest.mark.asyncio
async def test_create_role_with_existing_name_returns_409(roles):
    await _expect_error(_create([], name="一般"), 409, RoleError.NAME_EXISTS)
    assert roles == []


@pytest.mark.asyncio
async def test_create_role_racing_on_name_returns_409(monkeypatch, roles):
    """查詢時還不存在、寫入時撞到唯一約束 (連點或併發) —— 要回 409, 不是 500。"""

    class _UniqueViolationError(Exception):
        sqlstate = "23505"

    async def racing_create(data, session=None):
        raise IntegrityError("INSERT", {}, _UniqueViolationError())

    monkeypatch.setattr(RoleTable, "create", racing_create)

    await _expect_error(_create([], name="新角色"), 409, RoleError.NAME_EXISTS)


@pytest.mark.asyncio
async def test_update_role_to_existing_name_returns_409(roles):
    await _expect_error(
        _update("role-reader", name="超級管理者", permissions=[]),
        409,
        RoleError.NAME_EXISTS,
    )
    assert roles == []


@pytest.mark.asyncio
async def test_update_role_keeping_own_name_is_accepted(roles):
    """查到的同名角色就是自己, 不算重複。"""
    await _update("role-reader", name="一般", permissions=[], is_disabled=True)

    assert roles == [{"id": "role-reader", "name": "一般", "permissions": [], "is_disabled": True}]


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


# ── AUDIT 紀錄 ───────────────────────────────────────────────────────────────
#
# 「誰改了角色的權限」: 操作者來自這個請求的登入者 (`acting_as`), 不從參數傳。


@pytest.mark.asyncio
async def test_create_role_is_audited_with_actor_and_permissions(roles, audit_records):
    with acting_as("root"):
        await _create([])

    assert events(audit_records) == [
        (
            "role_created",
            {
                "request_id": "-",
                "actor": "root",
                "ip": "-",
                "role_id": "role-new",
                "permissions": "-",
            },
        )
    ]


@pytest.mark.asyncio
async def test_update_role_is_audited_with_actor_and_permissions(roles, audit_records):
    with acting_as("root"):
        await _update("role-reader", name="一般", permissions=[], is_disabled=True)

    [(event, fields)] = events(audit_records)
    assert event == "role_updated"
    assert fields["actor"] == "root"
    assert fields["role_id"] == "role-reader"
    assert fields["permissions"] == "-"
    assert fields["is_disabled"] == "True"


@pytest.mark.asyncio
async def test_disable_role_is_audited_with_actor(roles, audit_records):
    with acting_as("root"):
        await _disable("role-reader")

    audited = [
        (event, fields["actor"], fields["role_id"]) for event, fields in events(audit_records)
    ]
    assert audited == [("role_disabled", "root", "role-reader")]
