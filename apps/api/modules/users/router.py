from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query
from fastapi import Request as HttpRequest

from app.permissions import Permission
from shared.auth.contracts import CurrentUser
from shared.auth.dependency import check_user_permission
from shared.http.rate_limit import RateLimiter, client_ip
from shared.http.schema import PaginationParams

from . import service
from .schema import (
    BootstrapStatus,
    SignupRequest,
    SignupResponse,
    UserCreate,
    UserInfo,
    UserList,
    UserLogin,
    UserMe,
    UserOperate,
    UserResetPassword,
    UserToken,
    UserUpdate,
    UuidText,
)

router = APIRouter(prefix="/users", tags=["users"])

# 以 IP + 帳號為 key：只用 IP 會讓同一間辦公室的人互相影響，只用帳號則可被用來
# 惡意鎖定他人。成功登入後會 reset，正常使用者打錯幾次不會被卡住。
login_limiter = RateLimiter(max_attempts=10, window_seconds=300)
signup_limiter = RateLimiter(max_attempts=5, window_seconds=3600)


@router.post("/")
async def create_user_route(
    form_data: UserCreate,
    _=Depends(check_user_permission(Permission.USER_CREATE)),
) -> UserOperate:
    return await service.create_user(form_data)


@router.get("/bootstrap-status")
async def get_bootstrap_status_route(http_request: HttpRequest) -> BootstrapStatus:
    """還能不能用系統密碼建立第一個超級管理者。公開端點，不需認證。"""
    # 不需認證是必要的：註冊頁要在使用者登入之前決定顯示表單還是「系統已初始化」。
    # 因此回應只能是這一個布林值 —— 不要加上帳號、金鑰或任何可用來窮舉的資訊。
    return BootstrapStatus(
        available=await service.bootstrap_available(http_request.app.state.env.register_key)
    )


@router.post("/signup")
async def signup_user_route(
    http_request: HttpRequest,
    form_data: SignupRequest,
) -> SignupResponse:
    # 註冊是公開端點，且 register_key 可被暴力嘗試，所以以 IP 限流。
    signup_limiter.check(client_ip(http_request))
    result = await service.signup_user(
        form_data=form_data,
        expected_key=http_request.app.state.env.register_key,
    )
    signup_limiter.reset(client_ip(http_request))
    return result


@router.post("/login")
async def user_login_route(
    http_request: HttpRequest,
    form_data: Annotated[UserLogin, Form()],
) -> UserToken:
    rate_key = f"{client_ip(http_request)}:{form_data.username}"
    login_limiter.check(rate_key)
    result = await service.login_user(form_data, http_request.app.state.env)
    login_limiter.reset(rate_key)
    return result


@router.get("/me")
async def get_current_user_route(
    current_user: CurrentUser = Depends(check_user_permission()),
) -> UserMe:
    # 這裡的 dict 來自 auth dependency（`app.state.current_user_resolver`），不經 service，
    # 所以驗證要在這一層做 —— 少了它，resolver 回傳形狀變了只會在執行期炸。
    return UserMe.model_validate(current_user)


@router.get("/{id}")
async def get_user_route(
    id: UuidText,
    _=Depends(check_user_permission(Permission.USER_READ)),
) -> UserInfo:
    return await service.get_user(id)


@router.get("/")
async def get_user_list_route(
    pagination: Annotated[PaginationParams, Depends()],
    name: str | None = Query(default=None),
    role_id: str | None = Query(default=None),
    is_disabled: bool | None = Query(default=None),
    _=Depends(check_user_permission(Permission.USER_READ)),
) -> UserList:
    return await service.get_user_list(
        **pagination.model_dump(),
        name=name,
        role_id=role_id,
        is_disabled=is_disabled,
    )


@router.patch("/{id}")
async def update_user_route(
    http_request: HttpRequest,
    id: UuidText,
    form_data: UserUpdate,
    current_user: CurrentUser = Depends(
        check_user_permission(
            [Permission.USER_UPDATE_OWN, Permission.USER_UPDATE_ANY],
            mode="any",
        )
    ),
) -> UserOperate:
    return await service.update_user_profile(
        current_user=current_user,
        id=id,
        form_data=form_data,
        resolver=http_request.app.state.permission_resolver,
    )


@router.patch("/{id}/reset_password")
async def reset_user_password_route(
    id: UuidText,
    form_data: UserResetPassword,
    _=Depends(check_user_permission(Permission.USER_MANAGE)),
) -> UserOperate:
    return await service.reset_user_password(id, form_data)


@router.delete("/{id}")
async def disable_user_route(
    http_request: HttpRequest,
    id: UuidText,
    current_user: CurrentUser = Depends(check_user_permission(Permission.USER_DELETE)),
) -> UserOperate:
    return await service.disable_user(
        current_user=current_user,
        target_id=id,
        resolver=http_request.app.state.permission_resolver,
    )
