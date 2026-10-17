"""組裝出這個專案的 app。平台接線 (middleware、例外處理、lifespan) 在 `shared/platform.py`。"""

from fastapi import FastAPI

from app.config import APP_VERSION, CONTRACT_VERSION, env
from app.permissions import Permission
from app.registry import ENABLED_MODULES
from shared.module import ModuleManifest
from shared.platform import create_platform_app


def create_app(modules: tuple[ModuleManifest, ...] = ENABLED_MODULES) -> FastAPI:
    """測試可傳入部分 modules, 組出只掛那些模組的 app。"""
    return create_platform_app(
        env=env,
        modules=modules,
        permissions=Permission,
        title=env.project_name or "API",
        app_version=APP_VERSION,
        contract_version=CONTRACT_VERSION,
    )


app = create_app()
