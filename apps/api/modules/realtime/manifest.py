from shared.module import ModuleManifest

from .router import router

MODULE = ModuleManifest(name="realtime", routers=(router,))
