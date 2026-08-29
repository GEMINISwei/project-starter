from typing import Annotated

from pydantic import AfterValidator, BaseModel, StringConstraints

from app.permissions import Permission
from shared.http.errors import BaseError, LangText, resolve_text
from shared.http.schema import NonEmptyText, PaginatedResponse, UuidText

# 72 是 bcrypt 的硬限制（超過的位元組會被靜默截斷），不是我們挑的數字。
MAX_PASSWORD_BYTES = 72


class PasswordError(BaseError):
    TOO_LONG = LangText(
        zh=f"密碼不可超過 {MAX_PASSWORD_BYTES} bytes",
        en=f"Password must not exceed {MAX_PASSWORD_BYTES} bytes",
    )


def validate_password_bytes(value: str) -> str:
    # 這是 pydantic 的 validator，必須丟 ValueError 才會轉成 422（丟 LangException
    # 會變成未處理的例外），所以取的是解析後的字串 —— 同 shared/http/schema.py。
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(resolve_text(PasswordError.TOO_LONG.value))
    return value


Password = Annotated[str, StringConstraints(min_length=1), AfterValidator(validate_password_bytes)]
NewPassword = Annotated[
    str, StringConstraints(min_length=8), AfterValidator(validate_password_bytes)
]


class UserCreate(BaseModel):
    username: NonEmptyText
    password: NewPassword
    nickname: NonEmptyText
    role_ids: list[UuidText] | None = None

# CLI 專用（`scripts/db.py create-superuser`），不掛在任何端點上，所以不會進 OpenAPI。
# 存在的理由是讓 CLI 與 API 共用同一組 username／password 約束，而不是各寫一套規則。
# 不重用 UserCreate：那個模型帶 role_ids，而這裡的角色是固定的，
# 收一個會被忽略的欄位遲早會有人以為它有效。


class SuperAdminCreate(BaseModel):
    username: NonEmptyText
    password: NewPassword
    nickname: NonEmptyText


class SignupRequest(BaseModel):
    username: NonEmptyText
    password: NewPassword
    nickname: NonEmptyText
    register_key: NonEmptyText


class UserLogin(BaseModel):
    username: NonEmptyText
    password: Password


class UserUpdate(BaseModel):
    nickname: NonEmptyText
    is_disabled: bool
    role_ids: list[UuidText] | None = None


class UserResetPassword(BaseModel):
    password: NewPassword


class UserOperate(BaseModel):
    id: str


class SignupResponse(BaseModel):
    id: str


class BootstrapStatus(BaseModel):
    # True 代表「還沒有任何超級管理者，且 REGISTER_KEY 有設定」。
    # 前端據此決定要顯示註冊表單還是「系統已初始化」的訊息。
    available: bool


class UserToken(BaseModel):
    access_token: str
    token_type: str


class UserMe(BaseModel):
    id: str
    nickname: str
    role_ids: list[str]
    permissions: list[Permission]


class UserInfo(BaseModel):
    id: str
    username: str
    nickname: str
    role_ids: list[str]
    permissions: list[Permission]
    is_disabled: bool


class UserList(PaginatedResponse["UserInfo"]):
    pass
