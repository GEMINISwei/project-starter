from collections.abc import Awaitable, Callable

from fastapi import Request

from shared.http.errors import BaseError, LangException, LangText

from .contracts import CurrentUser, CurrentUserResolver, PermissionResolverProtocol
from .permissions import WILDCARD, BasePermission
from .tokens import TokenData, TokenError, parse_token


def is_current_auth_version(token_data: TokenData, current_user: CurrentUser) -> bool:
    """token 帶的世代是否仍與使用者當前的 `auth_version` 相符。

    這是「換密碼要能作廢已簽發的憑證」的唯一實作。日後多一種進入點 (例如短效 ticket)
    要呼叫它, 不要各寫一份 —— 漏掉一邊不會有任何症狀。
    """
    expected = current_user["auth_version"]
    return token_data["auth_version"] == expected


class DependencyError(BaseError):
    OPERATOR_NOT_FOUND = LangText(
        zh="操作者不存在",
        en="Operator Not Found",
    )
    OPERATOR_NO_PERMISSION = LangText(
        zh="操作者沒有權限",
        en="Operator Does Not Have Permission",
    )


def check_user_permission(
    permissions: (
        BasePermission
        | list[BasePermission]
        | tuple[BasePermission, ...]
        | set[BasePermission]
        | None
    ) = None,
    *,
    mode: str = "all",
) -> Callable[[Request], Awaitable[CurrentUser]]:
    if mode not in {"all", "any"}:
        raise ValueError("mode must be 'all' or 'any'")

    async def dependency(request: Request) -> CurrentUser:
        cookie_token = request.cookies.get("access_token", None)
        token_data = parse_token(cookie_token, request.app.state.env)

        # `app.state` 的型別是 Any, 取出時標上 Protocol 才拿回型別檢查。
        current_user_resolver: CurrentUserResolver = request.app.state.current_user_resolver
        resolver: PermissionResolverProtocol = request.app.state.permission_resolver

        current_user = await current_user_resolver(token_data["username"])
        if not current_user:
            raise LangException(401, DependencyError.OPERATOR_NOT_FOUND)
        if current_user["is_disabled"] is True:
            raise LangException(401, DependencyError.OPERATOR_NOT_FOUND)
        # 世代不符就是換密碼之前簽發的舊憑證。
        if not is_current_auth_version(token_data, current_user):
            raise LangException(401, TokenError.TOKEN_REVOKED)

        final_permissions = resolver.expand(set(current_user["permissions"]))
        if permissions:
            required_permissions = (
                [permissions] if isinstance(permissions, BasePermission) else list(permissions)
            )
            if WILDCARD not in final_permissions:
                checker = all if mode == "all" else any
                allowed = checker(
                    permission in final_permissions for permission in required_permissions
                )
                if not allowed:
                    raise LangException(403, DependencyError.OPERATOR_NO_PERMISSION)

        return current_user

    return dependency

