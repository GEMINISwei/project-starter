from fastapi import APIRouter, Depends
from fastapi import Request as HttpRequest

from app.permissions import Permission, PermissionCatalog
from shared.auth.dependency import check_user_permission

from .schema import PermissionInfo, PermissionList

router = APIRouter(prefix="/permissions", tags=["permissions"])


@router.get("/")
async def get_permission_list_route(
    http_request: HttpRequest,
    _=Depends(check_user_permission(Permission.ROLE_READ)),
) -> PermissionList:
    # 目錄從 `app.state` 取，不是 import 一份全域 —— 它屬於「這個 app 啟用了哪些 module」，
    # 而那是組裝層的決定（見 app/permissions.py 的檔頭）。
    catalog: PermissionCatalog = http_request.app.state.permission_catalog
    permissions = catalog.assignable_permissions()
    return PermissionList(
        list_data=[PermissionInfo.model_validate(item) for item in permissions],
        count=len(permissions),
    )
