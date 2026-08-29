from collections.abc import Awaitable, Callable

from fastapi import Request

from shared.http.errors import BaseError, LangException, LangText

from .contracts import CurrentUser, CurrentUserResolver, PermissionResolverProtocol
from .permissions import BasePermission
from .tokens import TokenData, TokenError, parse_token


def is_current_auth_version(token_data: TokenData, current_user: CurrentUser) -> bool:
    """token 帶的世代是否仍與使用者當前的 `auth_version` 相符。

    抽成函式是因為有兩個呼叫端：HTTP 的權限依賴（下方）與 WebSocket handshake
    （`modules/realtime/router.py`）。兩邊必須用同一套判斷 —— 只擋 HTTP 而漏掉 WS，等於留一條
    「重設密碼後仍可用舊 ticket 連上並長期保持」的路。

    使用者與 token 都必須帶有版本值；新建使用者的 model 預設為第 1 版。
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

        # `app.state` 上的東西型別是 Any（shared 刻意不 import core，見 contracts.py）。
        # 取出來時明確標上 Protocol，才真的拿回型別檢查 —— 否則 contracts.py 定義的契約
        # 只是文件，打錯方法名或參數仍然要等到執行期才會炸。
        current_user_resolver: CurrentUserResolver = request.app.state.current_user_resolver
        resolver: PermissionResolverProtocol = request.app.state.permission_resolver

        current_user = await current_user_resolver(token_data["username"])
        if not current_user:
            raise LangException(401, DependencyError.OPERATOR_NOT_FOUND)
        if current_user["is_disabled"] is True:
            raise LangException(401, DependencyError.OPERATOR_NOT_FOUND)
        # token 的世代必須與資料庫上的一致，否則就是重設密碼之前簽發的舊憑證。
        # 這裡幾乎不花成本 —— 使用者本來就已經為了權限檢查查出來了。
        if not is_current_auth_version(token_data, current_user):
            raise LangException(401, TokenError.TOKEN_REVOKED)

        final_permissions = resolver.expand(set(current_user["permissions"]))
        if permissions:
            required_permissions = (
                [permissions] if isinstance(permissions, BasePermission) else list(permissions)
            )
            if "*" not in final_permissions:
                checker = all if mode == "all" else any
                allowed = checker(
                    permission in final_permissions for permission in required_permissions
                )
                if not allowed:
                    raise LangException(403, DependencyError.OPERATOR_NO_PERMISSION)

        return current_user

    return dependency

