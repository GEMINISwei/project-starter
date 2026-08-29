"""給其他後端 module 使用的公開介面。"""

from .model import UserTable
from .service import create_super_admin

__all__ = ["UserTable", "create_super_admin"]
