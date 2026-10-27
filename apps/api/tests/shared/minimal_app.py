"""只靠 `shared/` 組出來的最小 app, 給平台測試用。

它的 OpenAPI 只有前端 `shared/` 假設後端一定有的 `Permission` 與 `Language` 兩個 schema。
"""

from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

from shared.auth.permissions import WILDCARD, BasePermission
from shared.http.errors import Language
from shared.module import ModuleManifest
from shared.platform import create_platform_app


# 不加 frozen: Protocol 的成員是可寫的變數, 唯讀屬性不算滿足它。
@dataclass
class MinimalEnv:
    project_name: str = "minimal"
    postgres_url: str = "postgresql+asyncpg://localhost/minimal"
    jwt_secret_key: str = "minimal_app_secret_key_at_least_32_chars"
    jwt_algorithm: Literal["HS256"] = "HS256"
    expire_hours: int = 1


class Permission(BasePermission):
    """新專案一開始的權限 enum: 只有萬用字元。"""

    ALL = WILDCARD


class PlatformContract(BaseModel):
    """把平台契約要求的兩個 enum 帶進 OpenAPI。"""

    permission: Permission
    language: Language


_router = APIRouter(prefix="/platform")


@_router.get("/contract")
async def platform_contract_route() -> PlatformContract:
    return PlatformContract(permission=Permission.ALL, language=Language.ZH)


CONTRACT_MODULE = ModuleManifest("platform-contract", routers=(_router,))


def create_minimal_app(*modules: ModuleManifest, app_version: str = "0") -> FastAPI:
    return create_platform_app(
        env=MinimalEnv(),
        modules=modules,
        permissions=Permission,
        title="minimal",
        app_version=app_version,
    )
