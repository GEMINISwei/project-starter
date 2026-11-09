"""roles 給其他模組的公開介面 (`modules/roles/public.py`)。

其他模組只透過這幾個函式取得角色資料, 不碰 `RoleTable` (理由見 `tests/test_architecture.py`
的 `test_module_public_entries_export_no_orm_tables`)。
"""

import uuid
from datetime import datetime
from typing import cast

import pytest

from modules.roles.model import RoleTable
from modules.roles.public import RoleDetail, expand_permissions, find_role_details


def _role(permissions: list[str], *, is_disabled: bool = False) -> RoleDetail:
    return cast(
        RoleDetail,
        {
            "id": str(uuid.uuid4()),
            "code": None,
            "name": "角色",
            "permissions": permissions,
            "is_disabled": is_disabled,
        },
    )


def test_expand_permissions_with_disabled_role_excludes_its_permissions():
    """停用一個角色要能立刻收回它的權限; 結果去重並排序, 比對時才不受指派順序影響。"""
    roles = [
        _role(["users:read", "roles:read"]),
        _role(["users:create"], is_disabled=True),
        _role(["users:read"]),
    ]

    assert expand_permissions(roles) == ["roles:read", "users:read"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_role_details_with_unknown_ids_returns_existing_in_creation_order(db):
    """不存在與格式不合法的 id 略過; 順序依建立時間, 使用者的 `role_ids` 才有穩定的順序。"""
    older = await RoleTable.create(
        data={"name": "先建", "permissions": [], "created_at": datetime(2026, 1, 1)}
    )
    newer = await RoleTable.create(
        data={"name": "後建", "permissions": [], "created_at": datetime(2026, 1, 2)}
    )

    result = await find_role_details([newer["id"], str(uuid.uuid4()), "not-a-uuid", older["id"]])

    assert [role["id"] for role in result] == [older["id"], newer["id"]]
