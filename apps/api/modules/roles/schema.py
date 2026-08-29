from pydantic import BaseModel

from app.permissions import Permission
from shared.http.schema import NonEmptyText, PaginatedResponse, SimpleListResponse
from shared.http.schema import UuidText as UuidText


class RoleCreate(BaseModel):
    name: NonEmptyText
    permissions: list[Permission] = []


class RoleUpdate(BaseModel):
    name: NonEmptyText
    permissions: list[Permission]
    is_disabled: bool


class RoleOperate(BaseModel):
    id: str


class RoleInfo(BaseModel):
    id: str
    code: str | None = None
    name: str
    permissions: list[Permission]
    is_disabled: bool


class RoleList(PaginatedResponse["RoleInfo"]):
    pass


class RoleOptionList(SimpleListResponse["RoleInfo"]):
    """`GET /roles/options` 的回應：非分頁的完整清單（list_data + count）。"""
