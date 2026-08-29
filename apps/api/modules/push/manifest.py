from shared.module import ModuleManifest

from .dispatcher import configure_push
from .model import PushSubscriptionTable
from .permissions import PERMISSIONS
from .router import router

MODULE = ModuleManifest(
    name="push",
    routers=(router,),
    tables=(PushSubscriptionTable,),
    permissions=PERMISSIONS,
    configure=configure_push,
)
