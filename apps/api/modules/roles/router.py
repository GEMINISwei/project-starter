from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.permissions import Permission
from shared.auth.dependency import check_user_permission
from shared.http.schema import PaginationParams

from . import service
from .schema import (
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
    _=Depends(check_user_permission(Permission.ROLE_CREATE)),
) -> RoleOperate:
    return await service.create_role(form_data)


# 放在 `/{id}` 之前：否則 "options" 會先被當成 id 吃掉。
@router.get("/options")
async def get_role_options_route(
    is_disabled: bool | None = Query(default=None),
    _=Depends(check_user_permission(Permission.ROLE_READ)),
) -> RoleOptionList:
    """非分頁的完整角色清單，供前端填下拉選單。"""
    # 與 `GET /roles/` 分開而不是加參數：一個端點只回傳一種形狀，OpenAPI 才標得準。
    return await service.get_role_options(is_disabled=is_disabled)


@router.get("/{id}")
async def get_role_route(
    id: UuidText,
    _=Depends(check_user_permission(Permission.ROLE_READ)),
) -> RoleInfo:
    return await service.get_role(id)


@router.get("/")
async def get_role_list_route(
    pagination: Annotated[PaginationParams, Depends()],
    name: str | None = Query(default=None),
    is_disabled: bool | None = Query(default=None),
    _=Depends(check_user_permission(Permission.ROLE_READ)),
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
    _=Depends(check_user_permission(Permission.ROLE_UPDATE)),
) -> RoleOperate:
    return await service.update_role(id, form_data)


# DELETE 但實際是停用（軟刪除）—— 角色被使用者參照著，真的刪掉會留下指向不存在角色的
# `role_ids`。函式名跟著 service 叫 disable，不要叫 delete：`modules/users` 的
# `disable_user_route` 同理，只有 `modules/items` 的 DELETE 是真刪除。
@router.delete("/{id}")
async def disable_role_route(
    id: UuidText,
    _=Depends(check_user_permission(Permission.ROLE_MANAGE)),
) -> RoleOperate:
    return await service.disable_role(id)
