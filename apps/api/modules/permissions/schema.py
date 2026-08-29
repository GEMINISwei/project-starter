from pydantic import BaseModel

from app.permissions import Permission
from shared.http.schema import SimpleListResponse


class PermissionInfo(BaseModel):
    # 刻意標成 Permission 而非 str：這樣 Permission enum 會完整出現在 OpenAPI schema 上，
    # 前端才能從產生的型別取得權限字面值聯集，不必手抄一份（見 shared/api/entities.ts）。
    value: Permission
    label: str


class PermissionList(SimpleListResponse["PermissionInfo"]):
    pass
