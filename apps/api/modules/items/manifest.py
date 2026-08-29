from shared.module import ModuleManifest

from .model import ItemTable
from .permissions import PERMISSIONS
from .router import router

MODULE = ModuleManifest(
    name="items",
    routers=(router,),
    tables=(ItemTable,),
    permissions=PERMISSIONS,
)
