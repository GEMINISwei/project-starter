from app.permissions import Permission
from shared.http.errors import LangText
from shared.module import PermissionSpec

PERMISSIONS = (
    PermissionSpec(Permission.USER_READ, LangText(zh="使用者：查看", en="Users: Read")),
    PermissionSpec(Permission.USER_CREATE, LangText(zh="使用者：建立", en="Users: Create")),
    PermissionSpec(
        Permission.USER_UPDATE_OWN,
        LangText(zh="使用者：更新自己", en="Users: Update Own"),
    ),
    PermissionSpec(
        Permission.USER_UPDATE_ANY,
        LangText(zh="使用者：更新任意使用者", en="Users: Update Any"),
        assignable=False,
    ),
    PermissionSpec(Permission.USER_DELETE, LangText(zh="使用者：停用使用者", en="Users: Disable")),
    PermissionSpec(
        Permission.USER_MANAGE,
        LangText(zh="使用者：管理", en="Users: Manage"),
        dependencies=frozenset(
            {
                Permission.USER_READ,
                Permission.USER_CREATE,
                Permission.USER_UPDATE_OWN,
                Permission.USER_UPDATE_ANY,
                Permission.USER_DELETE,
            }
        ),
    ),
)
