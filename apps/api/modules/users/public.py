"""給其他後端 module 使用的公開介面。"""

from .superuser import create_super_admin, revoke_all_sessions

__all__ = ["create_super_admin", "revoke_all_sessions"]
