from shared.module import ModuleManifest

from .model import RoleTable
from .permissions import PERMISSIONS
from .router import router

MODULE = ModuleManifest(
    name="roles",
    routers=(router,),
    tables=(RoleTable,),
    permissions=PERMISSIONS,
)
