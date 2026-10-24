from typing import TypedDict

import jwt
from jwt import PyJWTError

from shared.http.errors import BaseError, LangException, LangText
from shared.time import expires_at

from .contracts import AppEnvProtocol, TokenSubject


class TokenError(BaseError):
    TOKEN_NOT_FOUND = LangText(
        zh="登入資訊不存在，請重新登入",
        en="Token Not Found, Please Login Again",
    )
    TOKEN_INVALID = LangText(
        zh="無效的登入資訊，請重新登入",
        en="Token Invalid, Please Login Again",
    )
    TOKEN_REVOKED = LangText(
        zh="登入資訊已失效，請重新登入",
        en="Token Revoked, Please Login Again",
    )


# 用途標記, 由 `_decode` 比對。目前只有一種, 但要留著: 新增第二種短效憑證時, 它讓
# 「拿 A 當 B 用」在密碼學上就不成立。
SESSION_TOKEN_TYPE = "session"  # noqa: S105 —— 這是用途標記, 不是密碼


def _encode(payload: dict, env: AppEnvProtocol) -> str:
    return jwt.encode(payload, env.jwt_secret_key, algorithm=env.jwt_algorithm)


class TokenData(TypedDict):
    """解碼後的 token 內容 (`_decode` 保證欄位存在, TypedDict 讓這個保證留在型別上)。"""

    username: str
    auth_version: int


def _decode(token: str | None, env: AppEnvProtocol, *, expected_type: str) -> TokenData:
    if token is None:
        raise LangException(401, TokenError.TOKEN_NOT_FOUND)

    try:
        payload = jwt.decode(token, env.jwt_secret_key, algorithms=[env.jwt_algorithm])
    except PyJWTError as exc:
        # 過期與偽造都會落在這裡。
        raise LangException(401, TokenError.TOKEN_INVALID) from exc

    username = payload.get("username")
    system_name = payload.get("sn")
    token_type = payload.get("typ")
    auth_version = payload.get("uv")

    if (
        system_name != env.project_name
        or not isinstance(username, str)
        or type(auth_version) is not int
    ):
        raise LangException(401, TokenError.TOKEN_INVALID)
    if token_type != expected_type:
        raise LangException(401, TokenError.TOKEN_INVALID)
    return {"username": username, "auth_version": auth_version}


def create_token(user_data: TokenSubject, env: AppEnvProtocol) -> dict:
    token_data = {
        "exp": expires_at(hours=env.expire_hours),
        "username": user_data["username"],
        "sn": env.project_name,
        # 使用者自己的 token 世代, 換密碼、登出與全員撤銷時 +1。升級前簽發的 token
        # 另外帶著全站版號 `tv`, 解碼時不看它, 升級才不會把所有人踢下線。
        "uv": user_data["auth_version"],
        "typ": SESSION_TOKEN_TYPE,
    }

    return {
        "access_token": _encode(token_data, env),
        "token_type": "bearer",
    }


def parse_token(token: str | None, env: AppEnvProtocol) -> TokenData:
    return _decode(token, env, expected_type=SESSION_TOKEN_TYPE)
