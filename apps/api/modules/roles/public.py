"""給其他後端 module 使用的公開介面。

只轉出能力 (函式與它的回傳型別), 不轉出 `RoleTable`: 規則見 docs/architecture.md
〈模組之間的資料關聯〉。
"""

from .model import RoleDetail, expand_permissions, find_role_details, get_super_admin_role_id

__all__ = ["RoleDetail", "expand_permissions", "find_role_details", "get_super_admin_role_id"]
