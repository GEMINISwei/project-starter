from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query
from fastapi import Request as HttpRequest

from app.permissions import Permission
from shared.auth.contracts import CurrentUser
from shared.auth.dependency import check_user_permission
from shared.http.rate_limit import RateLimiter, client_ip
from shared.http.schema import PaginationParams

from . import account, bootstrap, service
from .schema import (
    BootstrapStatus,
    PasswordChange,
    ProfileUpdate,
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

# 以 IP + 帳號為 key: 只用 IP 會讓同一間辦公室互相影響, 只用帳號則可被拿來鎖定他人。
login_limiter = RateLimiter(max_attempts=10, window_seconds=300)
# 上面那層換個帳號名就是新的 key, 擋不住「同一個來源對整份帳號清單各試幾次」。
# 這一層只看 IP, 上限訂寬 (同一個 NAT 後面的整間辦公室要能正常登入),
# 而且成功**不 reset**: 否則攻擊者用自己的帳號登入一次就能把額度洗回來。
login_ip_limiter = RateLimiter(max_attempts=50, window_seconds=300)
signup_limiter = RateLimiter(max_attempts=5, window_seconds=3600)
# 以使用者 id 為 key。擋的主要是 bcrypt 的 CPU 消耗 (一個被盜的 session 不該變成 CPU
# 消耗器), 順帶讓偷到 cookie 的人無法慢慢試舊密碼。
password_change_limiter = RateLimiter(max_attempts=10, window_seconds=300)


@router.post("/")
async def create_user_route(
    form_data: UserCreate,
    _: CurrentUser = Depends(check_user_permission(Permission.ALL)),
) -> UserOperate:
    return await service.create_user(form_data=form_data)


@router.get("/bootstrap-status")
async def get_bootstrap_status_route(http_request: HttpRequest) -> BootstrapStatus:
    """還能不能用系統密碼建立第一個超級管理者。公開端點, 不需認證。"""
    # 公開端點, 所以回應只能是這一個布林值 —— 不要加上任何可用來窮舉的資訊。
    return BootstrapStatus(
        available=await bootstrap.bootstrap_available(http_request.app.state.env.register_key)
    )


@router.post("/signup")
async def signup_user_route(
    http_request: HttpRequest,
    form_data: SignupRequest,
) -> SignupResponse:
    signup_limiter.check(client_ip(http_request))
    result = await bootstrap.signup_user(
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
    ip = client_ip(http_request)
    login_ip_limiter.check(ip)
    rate_key = f"{ip}:{form_data.username}"
    login_limiter.check(rate_key)
    result = await account.login_user(form_data, http_request.app.state.env)
    login_limiter.reset(rate_key)
    return result


@router.get("/me")
async def get_current_user_route(
    http_request: HttpRequest,
    current_user: CurrentUser = Depends(check_user_permission()),
) -> UserMe:
    """目前登入者。`permissions` 是**展開相依之後**的完整集合。"""
    # 展開之後再交出去: 前端只比對字串、不認得相依關係, 只拿到「管理」的人在前端看來就沒有
    # 它展開出來的「查看」, 導覽與按鈕會全部消失 (後端卻允許)。
    # 這個 dict 不經 service, 所以在這一層驗證形狀。
    resolver = http_request.app.state.permission_resolver
    return UserMe.model_validate(
        {**current_user, "permissions": sorted(resolver.expand(set(current_user["permissions"])))}
    )


@router.patch("/me/password")
async def change_own_password_route(
    http_request: HttpRequest,
    form_data: PasswordChange,
    current_user: CurrentUser = Depends(check_user_permission()),
) -> UserToken:
    """更換自己的密碼。**不需要任何 permission** —— 每個登入的人都換得了自己的。

    回傳一張新的 access token: 換密碼會撤銷這個人所有既有的 session, 包含發出這次請求的
    那一張 (見 `account.change_own_password`)。呼叫端**必須**用它覆寫 cookie。
    """
    rate_key = current_user["id"]
    password_change_limiter.check(rate_key)
    result = await account.change_own_password(
        current_user=current_user,
        form_data=form_data,
        env=http_request.app.state.env,
    )
    password_change_limiter.reset(rate_key)
    return result


@router.patch("/me")
async def update_own_profile_route(
    form_data: ProfileUpdate,
    current_user: CurrentUser = Depends(check_user_permission()),
) -> UserOperate:
    """更新自己的個人資料。**不需要任何 permission** —— 每個登入的人都改得了自己的。"""
    return await account.update_own_profile(current_user=current_user, form_data=form_data)


@router.post("/me/logout")
async def logout_route(
    current_user: CurrentUser = Depends(check_user_permission()),
) -> UserOperate:
    """登出。這個帳號在所有裝置上的登入都會失效, 其他使用者不受影響。"""
    return await account.logout_user(current_user)


@router.get("/{id}")
async def get_user_route(
    id: UuidText,
    _: CurrentUser = Depends(check_user_permission(Permission.ALL)),
) -> UserInfo:
    return await service.get_user(id)


@router.get("/")
async def get_user_list_route(
    pagination: Annotated[PaginationParams, Depends()],
    name: str | None = Query(default=None),
    role_id: str | None = Query(default=None),
    is_disabled: bool | None = Query(default=None),
    _: CurrentUser = Depends(check_user_permission(Permission.ALL)),
) -> UserList:
    return await service.get_user_list(
        **pagination.model_dump(),
        name=name,
        role_id=role_id,
        is_disabled=is_disabled,
    )


@router.patch("/{id}")
async def update_user_route(
    id: UuidText,
    form_data: UserUpdate,
    current_user: CurrentUser = Depends(check_user_permission(Permission.ALL)),
) -> UserOperate:
    return await service.update_user(current_user=current_user, id=id, form_data=form_data)


@router.patch("/{id}/reset-password")
async def reset_user_password_route(
    id: UuidText,
    form_data: UserResetPassword,
    _: CurrentUser = Depends(check_user_permission(Permission.ALL)),
) -> UserOperate:
    return await service.reset_user_password(id=id, form_data=form_data)


@router.delete("/{id}")
async def disable_user_route(
    id: UuidText,
    current_user: CurrentUser = Depends(check_user_permission(Permission.ALL)),
) -> UserOperate:
    return await service.disable_user(current_user=current_user, target_id=id)
