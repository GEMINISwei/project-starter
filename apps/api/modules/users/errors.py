from shared.http.errors import BaseError, LangText


class UserError(BaseError):
    NOT_FOUND = LangText(zh="用戶不存在", en="User Not Found")
    USERNAME_EXISTS = LangText(zh="帳號已存在", en="Username Already Exists")
    INVALID_CREDENTIALS = LangText(zh="帳號或密碼錯誤", en="Invalid Username or Password")
    CANNOT_DISABLE_SUPER = LangText(zh="無法停用超級管理者帳號", en="Cannot Disable Super Admin")
    CANNOT_DISABLE_SELF = LangText(zh="無法停用自己的帳號", en="Cannot Disable Self")
    CURRENT_PASSWORD_MISMATCH = LangText(zh="目前密碼錯誤", en="Current Password Is Incorrect")
    ROLE_NOT_FOUND = LangText(zh="角色不存在", en="Role Not Found")
    ROLE_DISABLED = LangText(zh="角色已停用", en="Role Disabled")
    CANNOT_RESET_SUPER_PASSWORD = LangText(
        zh="無法在後台重設超級管理者的密碼",
        en="Cannot Reset Super Admin Password",
    )
    CANNOT_CHANGE_SUPER_ROLES = LangText(
        zh="無法更改超級管理者的角色",
        en="Cannot Change Super Admin Roles",
    )
    CANNOT_ASSIGN_SUPER_ADMIN = LangText(
        zh="無法指派超級管理者角色",
        en="Cannot Assign Super Admin Role",
    )
