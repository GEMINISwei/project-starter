from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi import Request as HttpRequest

from app.permissions import Permission
from shared.auth.contracts import CurrentUser
from shared.auth.dependency import check_user_permission
from shared.http.schema import PaginationParams

from . import service
from .schema import (
    PermissionOptionList,
    RoleCreate,
    RoleInfo,
    RoleList,
    RoleOperate,
    RoleOptionList,
    RoleUpdate,
    UuidText,
)

router = APIRouter(prefix="/roles", tags=["roles"])


@router.post("/")
async def create_role_route(
    form_data: RoleCreate,
    _: CurrentUser = Depends(check_user_permission(Permission.ALL)),
) -> RoleOperate:
    return await service.create_role(form_data=form_data)


# 這條與下一條都要放在 `/{id}` 之前: 否則 "options" 會先被當成 id 吃掉。
@router.get("/options")
async def get_role_options_route(
    is_disabled: bool | None = Query(default=None),
    _: CurrentUser = Depends(check_user_permission(Permission.ALL)),
) -> RoleOptionList:
    """非分頁的完整角色清單, 供前端填下拉選單。"""
    # 與 `GET /roles/` 分開而不是加參數: 一個端點只回傳一種形狀, OpenAPI 才標得準。
    return await service.get_role_options(is_disabled=is_disabled)


@router.get("/permission-options")
async def get_permission_options_route(
    http_request: HttpRequest,
    _: CurrentUser = Depends(check_user_permission(Permission.ALL)),
) -> PermissionOptionList:
    """角色可以勾選的權限, 含分類與目前語系的標籤。"""
    # 目錄從 `app.state` 取, 不是 import 一份全域 —— 它屬於「這個 app 啟用了哪些 module」,
    # 而那是組裝層的決定 (見 shared/auth/catalog.py 的檔頭)。
    return service.get_permission_options(http_request.app.state.permission_catalog)


@router.get("/{id}")
async def get_role_route(
    id: UuidText,
    _: CurrentUser = Depends(check_user_permission(Permission.ALL)),
) -> RoleInfo:
    return await service.get_role(id)


@router.get("/")
async def get_role_list_route(
    pagination: Annotated[PaginationParams, Depends()],
    name: str | None = Query(default=None),
    is_disabled: bool | None = Query(default=None),
    _: CurrentUser = Depends(check_user_permission(Permission.ALL)),
) -> RoleList:
    return await service.get_role_list(
        **pagination.model_dump(),
        name=name,
        is_disabled=is_disabled,
    )


@router.patch("/{id}")
async def update_role_route(
    id: UuidText,
    form_data: RoleUpdate,
    _: CurrentUser = Depends(check_user_permission(Permission.ALL)),
) -> RoleOperate:
    return await service.update_role(id=id, form_data=form_data)


# DELETE 但實際是停用 (軟刪除) —— 角色被使用者參照著, 真的刪掉會留下指向不存在角色的
# `role_ids`。函式名跟著 service 叫 disable, 不要叫 delete: `modules/users` 的
# `disable_user_route` 同理 —— 這個模板裡沒有任何 DELETE 是真刪除。
@router.delete("/{id}")
async def disable_role_route(
    id: UuidText,
    _: CurrentUser = Depends(check_user_permission(Permission.ALL)),
) -> RoleOperate:
    return await service.disable_role(id=id)
