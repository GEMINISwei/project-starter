"""給其他後端 module 使用的公開介面。"""

from .bootstrap import create_super_admin

__all__ = ["create_super_admin"]
