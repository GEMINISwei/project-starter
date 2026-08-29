"""**範例模組**的路由。用不到時整包刪除，見 docs/architecture.md「移除 module」。

router 與 Document 由本模組的 `manifest.py` 明確註冊，再由 `app.registry` 組裝。
新增模組時照這個結構建立目錄並加入中央啟用清單。
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.permissions import Permission
from shared.auth.contracts import CurrentUser
from shared.auth.dependency import check_user_permission
from shared.http.schema import PaginationParams

from . import service
from .schema import ItemCreate, ItemInfo, ItemList, ItemOperate, ItemUpdate, UuidText

router = APIRouter(prefix="/items", tags=["items"])


@router.post("/")
async def create_item_route(
    form_data: ItemCreate,
    current_user: CurrentUser = Depends(check_user_permission(Permission.ITEM_CREATE)),
) -> ItemOperate:
    return await service.create_item(
        form_data=form_data,
        current_user_id=current_user["id"],
    )


@router.get("/{id}")
async def get_item_route(
    id: UuidText,
    _=Depends(check_user_permission(Permission.ITEM_READ)),
) -> ItemInfo:
    return await service.get_item(id)


@router.get("/")
async def get_item_list_route(
    pagination: Annotated[PaginationParams, Depends()],
    name: str | None = Query(default=None),
    is_disabled: bool | None = Query(default=None),
    _=Depends(check_user_permission(Permission.ITEM_READ)),
) -> ItemList:
    """游標分頁的列表。`limit` 是必填，回應一律是分頁形狀。"""
    # 需要非分頁的完整清單時，請另開一條路由搭配 `SimpleListResponse`
    #（範例見 `GET /roles/options`），不要讓同一個端點依參數回傳兩種形狀 ——
    # 回應型別只能標其中一種。
    return await service.get_item_list(
        **pagination.model_dump(),
        name=name,
        is_disabled=is_disabled,
    )


@router.patch("/{id}")
async def update_item_route(
    id: UuidText,
    form_data: ItemUpdate,
    _=Depends(check_user_permission(Permission.ITEM_UPDATE)),
) -> ItemOperate:
    return await service.update_item(id, form_data)


@router.delete("/{id}")
async def delete_item_route(
    id: UuidText,
    _=Depends(check_user_permission(Permission.ITEM_DELETE)),
) -> ItemOperate:
    return await service.delete_item(id)
