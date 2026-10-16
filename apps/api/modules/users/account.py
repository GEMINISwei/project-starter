"""使用者對**自己**帳號的操作: 登入、登出、更換自己的密碼、更新個人資料。

與 `service.py` (管理者對任意使用者的操作) 分開: 這裡的授權模型是「你就是這個帳號」,
不看 permission。
"""

from shared.auth import passwords
from shared.auth.contracts import AppEnvProtocol, CurrentUser
from shared.auth.tokens import create_token
from shared.http.errors import LangException, ensure_found

from .errors import UserError
from .model import UserTable
from .schema import PasswordChange, ProfileUpdate, UserLogin, UserOperate, UserToken


async def login_user(form_data: UserLogin, env: AppEnvProtocol) -> UserToken:
    user_data = await UserTable.find_detail_by_username(
        username=form_data.username,
        include_password=True,
    )
    # 帳號不存在時也要比對一次 (見 `verify_login_password`), 所以先比對、再判斷存不存在。
    password_matched = await passwords.verify_login_password(
        form_data.password, None if user_data is None else user_data["password"]
    )
    if user_data is None or user_data["is_disabled"] or not password_matched:
        raise LangException(401, UserError.INVALID_CREDENTIALS)

    return UserToken.model_validate(create_token(user_data, env))


async def change_own_password(
    current_user: CurrentUser,
    form_data: PasswordChange,
    env: AppEnvProtocol,
) -> UserToken:
    """使用者更換自己的密碼, 並拿回一張**新的** token。

    與 `service.reset_user_password` 不同: 要驗舊密碼、不需要 permission、會把新 token 交回去。
    換密碼會連自己手上這一張一起作廢, 補簽之後才是「其他裝置登出, 只有我還在」。

    **舊密碼不符不能回 401**: 前端把 401 一律解釋成 session 過期並導回登入頁,
    「密碼打錯一個字」會變成「被登出」。所以是 403。
    """
    user_data = ensure_found(
        await UserTable.find_detail_by_username(
            username=current_user["username"],
            include_password=True,
        ),
        UserError.NOT_FOUND,
    )

    if not await passwords.verify_password_async(
        plain_password=form_data.current_password,
        hashed_password=user_data["password"],
    ):
        raise LangException(403, UserError.CURRENT_PASSWORD_MISMATCH)

    # bcrypt 要在進入資料庫操作之前算完, 交易才不會多持有鎖 100–300ms。
    password_hash = await passwords.hash_password_async(form_data.new_password)

    updated = ensure_found(
        await UserTable.set_password_and_revoke_sessions(
            id=current_user["id"],
            password_hash=password_hash,
        ),
        UserError.NOT_FOUND,
    )

    return UserToken.model_validate(
        create_token(
            {
                "username": current_user["username"],
                # 用資料庫回來的那個值, 不要用 `current_user["auth_version"] + 1`
                # (理由見 `set_password_and_revoke_sessions` 的 docstring)。
                "auth_version": updated["auth_version"],
            },
            env,
        )
    )


async def logout_user(current_user: CurrentUser) -> UserOperate:
    """登出: 撤銷這個帳號**所有裝置**的 session, 不只是發出請求的這一台。

    token 是無狀態的, 只刪瀏覽器的 cookie 的話, 已經被複製出去的 token 到期前仍然有效。
    把世代號 +1 走的是與換密碼同一條撤銷路徑; 代價是登出會讓這個帳號的其他裝置一起登出。
    其他使用者不受影響 (世代號存在每個帳號自己的那一列上)。
    """
    return UserOperate.model_validate(
        ensure_found(await UserTable.revoke_sessions(id=current_user["id"]), UserError.NOT_FOUND)
    )


async def update_own_profile(current_user: CurrentUser, form_data: ProfileUpdate) -> UserOperate:
    # id 從 token 來, 不從請求內容來: 這條路徑不看 permission, 能改的只有發出請求的人自己。
    return UserOperate.model_validate(
        ensure_found(
            await UserTable.update_by_id(
                id=current_user["id"], data={"nickname": form_data.nickname}
            ),
            UserError.NOT_FOUND,
        )
    )
