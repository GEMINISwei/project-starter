from shared.module import ModuleManifest

from .bootstrap_model import SystemStateTable
from .model import UserTable
from .permissions import PERMISSIONS
from .router import router

MODULE = ModuleManifest(
    name="users",
    routers=(router,),
    tables=(SystemStateTable, UserTable),
    permissions=PERMISSIONS,
    # 使用者資料歸這個 module 所有，所以「怎麼依 username 取得目前使用者」也由它提供。
    # 回傳的是帶展開後 permissions 的 dict（見 UserTable.find_detail_by_username）。
    current_user_resolver=UserTable.find_detail_by_username,
)
