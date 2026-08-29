from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi import Request as HttpRequest

from app.permissions import Permission
from shared.auth.contracts import CurrentUser
from shared.auth.dependency import check_user_permission
from shared.http.schema import NonEmptyText

from . import service
from .schema import (
    AdminBroadcast,
    RegisterSubscription,
    SubscriptionOperate,
    VapidKey,
)

router = APIRouter(prefix="/push", tags=["push"])


@router.get("/vapid-public-key")
async def get_vapid_key_route(
    http_request: HttpRequest,
    _=Depends(check_user_permission()),
) -> VapidKey:
    return VapidKey(public_key=http_request.app.state.env.vapid_public_key)


@router.post("/subscriptions")
async def register_subscription_route(
    body: RegisterSubscription,
    current_user: CurrentUser = Depends(check_user_permission()),
) -> SubscriptionOperate:
    return await service.upsert_subscription(user_id=current_user["id"], data=body)


@router.delete("/subscriptions")
async def remove_subscription_route(
    endpoint: Annotated[NonEmptyText, Query()],
    current_user: CurrentUser = Depends(check_user_permission()),
) -> SubscriptionOperate:
    # endpoint 走 query 而不是 request body。帶 body 的 DELETE 不是標準做法（中間的
    # proxy 與部分 client 會直接把它丟掉），而且前端的型別層只為 query／path 參數推導
    # DELETE 的簽名 —— 用 body 的話呼叫端就只能繞過 `apiDelete` 自己手寫 fetch，
    # 而手寫的那一份不受契約保護。
    return await service.remove_subscription(user_id=current_user["id"], endpoint=endpoint)


@router.post("/test")
async def test_push_route(
    current_user: CurrentUser = Depends(check_user_permission()),
) -> SubscriptionOperate:
    # 只推給呼叫者自己，任何已登入使用者都能確認自己的推播設定。
    return await service.send_test_push(user_id=current_user["id"])


@router.post("/send")
async def broadcast_push_route(
    body: AdminBroadcast,
    _=Depends(check_user_permission(Permission.PUSH_SEND)),
) -> SubscriptionOperate:
    """推播給所有訂閱者（需要 push:send 權限）。"""
    return await service.broadcast(body)
