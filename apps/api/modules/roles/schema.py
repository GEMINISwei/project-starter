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
    """`GET /roles/options` 的回應: 非分頁的完整清單 (list_data + count)。"""


class PermissionInfo(BaseModel):
    """一個可以指派給角色的權限。畫面依 `category` 分組, 組內顯示 `label`。"""

    # 刻意標成 Permission 而非 str: 這樣前端拿到的是權限字面值聯集, 不是任意字串。
    value: Permission
    label: str
    category: str


class PermissionOptionList(SimpleListResponse["PermissionInfo"]):
    """`GET /roles/permission-options` 的回應, 依各 module 的宣告順序排列。"""
