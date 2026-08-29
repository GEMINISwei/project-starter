from app.permissions import Permission
from shared.http.errors import LangText
from shared.module import PermissionSpec

PERMISSIONS = (
    PermissionSpec(Permission.ITEM_READ, LangText(zh="項目：查看", en="Items: Read")),
    PermissionSpec(Permission.ITEM_CREATE, LangText(zh="項目：建立", en="Items: Create")),
    PermissionSpec(Permission.ITEM_UPDATE, LangText(zh="項目：更新", en="Items: Update")),
    PermissionSpec(Permission.ITEM_DELETE, LangText(zh="項目：刪除", en="Items: Delete")),
    PermissionSpec(
        Permission.ITEM_MANAGE,
        LangText(zh="項目：管理", en="Items: Manage"),
        dependencies=frozenset(
            {
                Permission.ITEM_READ,
                Permission.ITEM_CREATE,
                Permission.ITEM_UPDATE,
                Permission.ITEM_DELETE,
            }
        ),
    ),
)
