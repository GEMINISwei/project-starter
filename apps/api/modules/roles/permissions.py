from app.permissions import Permission
from shared.http.errors import LangText
from shared.module import PermissionSpec

PERMISSIONS = (
    PermissionSpec(Permission.ROLE_READ, LangText(zh="角色：查看", en="Roles: Read")),
    PermissionSpec(Permission.ROLE_CREATE, LangText(zh="角色：建立", en="Roles: Create")),
    PermissionSpec(Permission.ROLE_UPDATE, LangText(zh="角色：更新", en="Roles: Update")),
    PermissionSpec(
        Permission.ROLE_MANAGE,
        LangText(zh="角色：管理", en="Roles: Manage"),
        dependencies=frozenset(
            {Permission.ROLE_READ, Permission.ROLE_CREATE, Permission.ROLE_UPDATE}
        ),
    ),
)
