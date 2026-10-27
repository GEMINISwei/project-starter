from shared.module import ModuleManifest

from .model import RoleTable
from .router import router

MODULE = ModuleManifest(
    name="roles",
    routers=(router,),
    tables=(RoleTable,),
)
