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


# token 的用途標記。分成兩種型別是為了讓「拿 A 當 B 用」在密碼學上就不成立：
# WebSocket ticket 會出現在網址列（WS 沒有辦法帶 httpOnly cookie 以外的自訂 header），
# 如果它跟 session token 是同一種東西，等於把長效登入憑證寫進 URL、nginx log 與瀏覽器歷史。
SESSION_TOKEN_TYPE = "session"  # noqa: S105 —— 這是用途標記，不是密碼
WS_TICKET_TYPE = "ws"

# ticket 只用來完成一次 WebSocket handshake，60 秒綽綽有餘。它**不是**用過即廢的，TTL 內可以
# 重複使用（要做到一次性需要跨行程的共享狀態）—— 改長這個值等於放大外洩後的可用時間。
WS_TICKET_TTL_SECONDS = 60


def _encode(payload: dict, env: AppEnvProtocol) -> str:
    return jwt.encode(payload, env.jwt_secret_key, algorithm=env.jwt_algorithm)


class TokenData(TypedDict):
    """解碼後的 token 內容。

    標成 TypedDict 而不是裸 `dict`：`_decode` 已經保證 `username` 存在且非 None
    （不符合就丟 401），但回傳 `dict` 會讓這個保證在型別上消失，呼叫端只好寫
    `token_data.get("username")`，拿到 `Any | None`。
    """

    username: str
    auth_version: int


def _decode(token: str | None, env: AppEnvProtocol, *, expected_type: str) -> TokenData:
    if token is None:
        raise LangException(401, TokenError.TOKEN_NOT_FOUND)

    try:
        payload = jwt.decode(token, env.jwt_secret_key, algorithms=[env.jwt_algorithm])
    except PyJWTError as exc:
        # PyJWTError 是 PyJWT 所有例外的共同基底（含 ExpiredSignatureError、
        # InvalidSignatureError、DecodeError），所以過期與偽造都會落在這裡。
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
    if payload.get("tv") != env.token_version:
        raise LangException(401, TokenError.TOKEN_REVOKED)

    return {"username": username, "auth_version": auth_version}


def create_token(user_data: TokenSubject, env: AppEnvProtocol) -> dict:
    token_data = {
        "exp": expires_at(hours=env.expire_hours),
        "username": user_data["username"],
        "sn": env.project_name,
        # 不要改接 app version：那會讓每次改版本號都把所有人踢下線。只有明確要作廢全站既有
        # token 時才調整 TOKEN_VERSION。
        "tv": env.token_version,
        # 這個使用者自己的 token 世代。重設密碼會把資料庫裡的值 +1，於是所有帶著
        # 舊 `uv` 的 token（含 WS ticket）在下一次請求就被拒絕。
        "uv": user_data["auth_version"],
        "typ": SESSION_TOKEN_TYPE,
    }

    return {
        "access_token": _encode(token_data, env),
        "token_type": "bearer",
    }


def parse_token(token: str | None, env: AppEnvProtocol) -> TokenData:
    return _decode(token, env, expected_type=SESSION_TOKEN_TYPE)


def create_ws_ticket(username: str, env: AppEnvProtocol, auth_version: int) -> str:
    """簽發只能用來開 WebSocket 的短效憑證。

    由已通過 cookie 驗證的 HTTP 端點簽發（見 `modules/realtime/router.py`），瀏覽器拿到後只用於
    handshake。它**不能**當成 session token 使用（`typ` 不同，`parse_token` 會拒絕）。

    `auth_version` 一樣要帶：ticket 雖然只有 60 秒，但 WebSocket 連線本身是長效的。
    少了這個 claim，重設密碼之後仍握著舊 ticket 的人可以再開一條連線並一直留著。
    """
    ticket_data = {
        "exp": expires_at(seconds=WS_TICKET_TTL_SECONDS),
        "username": username,
        "sn": env.project_name,
        "tv": env.token_version,
        "uv": auth_version,
        "typ": WS_TICKET_TYPE,
    }

    return _encode(ticket_data, env)


def parse_ws_ticket(ticket: str | None, env: AppEnvProtocol) -> TokenData:
    return _decode(ticket, env, expected_type=WS_TICKET_TYPE)
