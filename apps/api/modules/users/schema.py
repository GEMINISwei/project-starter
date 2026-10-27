from typing import Annotated

from pydantic import AfterValidator, BaseModel, StringConstraints

from app.permissions import Permission
from shared.auth.passwords import MAX_PASSWORD_BYTES
from shared.http.errors import BaseError, LangText, resolve_text
from shared.http.schema import NonEmptyText, PaginatedResponse, UuidText


class PasswordError(BaseError):
    TOO_LONG = LangText(
        zh=f"密碼不可超過 {MAX_PASSWORD_BYTES} bytes",
        en=f"Password must not exceed {MAX_PASSWORD_BYTES} bytes",
    )


def validate_password_bytes(value: str) -> str:
    # 這是 pydantic 的 validator, 必須丟 ValueError 才會轉成 422 (丟 LangException
    # 會變成未處理的例外), 所以取的是解析後的字串 —— 同 shared/http/schema.py。
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


# CLI 專用 (`scripts/db.py create-superuser`), 不掛在任何端點上, 所以不會進 OpenAPI。
# 存在的理由是讓 CLI 與 API 的建立使用者共用同一組 username/password 約束, 而不是各寫一套規則。
# 不重用 UserCreate: 那個模型帶 role_ids, 而這裡的角色是固定的,
# 收一個會被忽略的欄位遲早會有人以為它有效。
class SuperAdminCreate(BaseModel):
    username: NonEmptyText
    password: NewPassword
    nickname: NonEmptyText


class UserLogin(BaseModel):
    username: NonEmptyText
    password: Password


class UserUpdate(BaseModel):
    nickname: NonEmptyText
    is_disabled: bool
    role_ids: list[UuidText] | None = None


# 與 UserUpdate 分開: 那個帶角色與停用狀態, 是超級管理者對任意使用者用的。自己改自己的
# 只能動個人資料, 用另一個模型讓多送的欄位在驗證時就被丟掉, 不必靠 service 記得忽略。
class ProfileUpdate(BaseModel):
    nickname: NonEmptyText


class UserResetPassword(BaseModel):
    password: NewPassword


class PasswordChange(BaseModel):
    """使用者更換**自己**的密碼 (`UserResetPassword` 是管理者替別人重設, 不需要舊密碼)。

    `current_password` 用 `Password` (只要求非空) 而不是 `NewPassword`: 它要比對的是一把
    **已經存在**的密碼, 可能是在規則變嚴之前設的。拿新規則去擋它, 會讓最應該換密碼的那批
    人反而換不了 —— 而且那個錯誤會出現在「目前密碼」欄位上, 看起來像打錯了。
    """

    current_password: Password
    new_password: NewPassword


class UserOperate(BaseModel):
    id: str


class SessionRevocation(BaseModel):
    affected: int


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
