"""超級管理者對**任意**使用者的操作: 建立、查詢、修改、重設密碼、停用。

這些端點只開放給 `Permission.ALL` (見 router), 所以這裡不再判斷「操作者能不能對這個人做」,
只留不論是誰都不該做的事: 停用自己; 停用超級管理者、改他的角色、重設他的密碼 (否則一位超管
可以把其他超管鎖在系統外); 指派超級管理者角色。

使用者對自己帳號的操作 (登入、改自己的密碼與個人資料) 在 `account.py`; 建立超級管理者在
`superuser.py`。
"""

from typing import Any, Literal

from sqlalchemy.exc import IntegrityError

from app.permissions import Permission
from modules.roles.public import RoleTable
from shared.auth import passwords
from shared.auth.contracts import CurrentUser
from shared.db.session import release_connection
from shared.db.table import is_unique_violation
from shared.http.errors import LangException, ensure_found

from .errors import UserError
from .model import UserDetail, UserTable
from .schema import (
    UserCreate,
    UserInfo,
    UserList,
    UserOperate,
    UserResetPassword,
    UserUpdate,
)


def _ensure_can_disable(
    current_user: CurrentUser,
    # target 是從 DB 查出的**任意**使用者, 不是通過認證的那一位 —— 形狀與 CurrentUser 不同
    # (帶 nickname、role_ids), 所以用 users 自己的 UserDetail 而不是 shared 的 CurrentUser。
    target: UserDetail,
) -> None:
    """停用的保護規則: 不能停用自己、不能停用超級管理者。

    停用有兩個入口 (`DELETE /users/{id}` 與 `PATCH` 帶 `is_disabled=true`), 規則只寫這一份 ——
    兩邊各寫的話, 日後加一條規則只會有一邊跟上。
    """
    if current_user["id"] == target["id"]:
        raise LangException(403, UserError.CANNOT_DISABLE_SELF)
    # 不必先展開相依: `*` 不會是任何權限的相依, 只可能直接掛在角色上。
    if Permission.ALL in target["permissions"]:
        raise LangException(403, UserError.CANNOT_DISABLE_SUPER)


async def create_user(form_data: UserCreate) -> UserOperate:
    """由超級管理者建立一般使用者。**這條路徑永遠不能建立超級管理者。**

    超級管理者只能由 CLI 建立 (`superuser.py`); 一般使用者建立流程不能繞過角色驗證。
    """
    if await UserTable.find_detail_by_username(username=form_data.username):
        raise LangException(409, UserError.USERNAME_EXISTS)

    role_ids = form_data.role_ids or []

    await validate_role_ids(role_ids)

    try:
        return UserOperate.model_validate(
            await UserTable.create(
                data={
                    "username": form_data.username,
                    "nickname": form_data.nickname,
                    # 逐欄列出而不是 `**model_dump()`: 日後往 UserCreate 加的敏感欄位
                    # 才不會沒經處理就直接落地。
                    "password": await passwords.hash_password_async(form_data.password),
                    "role_ids": role_ids,
                }
            )
        )
    except IntegrityError as exc:
        if not is_unique_violation(exc):
            raise
        raise LangException(409, UserError.USERNAME_EXISTS) from exc


async def get_user(id: str) -> UserInfo:
    return UserInfo.model_validate(
        ensure_found(await UserTable.find_detail_by_id(id), UserError.NOT_FOUND)
    )


async def get_user_list(
    limit: int,
    cursor: str | None = None,
    direction: Literal["next", "prev"] = "next",
    name: str | None = None,
    role_id: str | None = None,
    is_disabled: bool | None = None,
) -> UserList:
    return UserList.model_validate(
        await UserTable.find_list(
            cursor=cursor,
            direction=direction,
            limit=limit,
            name=name,
            role_id=role_id,
            is_disabled=is_disabled,
        )
    )


async def update_user(
    current_user: CurrentUser,
    id: str,
    form_data: UserUpdate,
) -> UserOperate:
    # 先確認目標存在, 否則不存在的 id 會變成 500 而不是 404。下面的停用分支也複用這筆。
    target = ensure_found(await UserTable.find_detail_by_id(id), UserError.NOT_FOUND)

    # 否則 mypy 會從第一個鍵推論成 dict[str, str]。
    update_data: dict[str, Any] = {
        "nickname": form_data.nickname,
    }

    if form_data.role_ids is not None:
        # 同 `_ensure_can_disable`: `*` 只可能直接掛在角色上, 不必先展開相依。
        if Permission.ALL in target["permissions"]:
            raise LangException(403, UserError.CANNOT_CHANGE_SUPER_ROLES)
        await validate_role_ids(form_data.role_ids)
        update_data["role_ids"] = form_data.role_ids

    if form_data.is_disabled is True:
        _ensure_can_disable(current_user, target)
    update_data["is_disabled"] = form_data.is_disabled

    # 再包一次 ensure_found: 查到之後、更新之前文件仍可能被刪掉。
    return UserOperate.model_validate(
        ensure_found(await UserTable.update_by_id(id=id, data=update_data), UserError.NOT_FOUND)
    )


async def reset_user_password(id: str, form_data: UserResetPassword) -> UserOperate:
    # 同 update_user: 不存在的 id 若不在這裡擋下, 會變成 500 而不是 404。
    target = ensure_found(await UserTable.find_detail_by_id(id), UserError.NOT_FOUND)
    # 包含自己: 能呼叫這個端點的只有超管。改自己的密碼走 `/users/me/password`。
    if Permission.ALL in target["permissions"]:
        raise LangException(403, UserError.CANNOT_RESET_SUPER_PASSWORD)

    # bcrypt 期間不佔連線 (理由見 `release_connection`)。
    await release_connection()
    password_hash = await passwords.hash_password_async(form_data.password)

    # 同時把 auth_version +1, 這個人所有既有的 session 立刻失效。
    return UserOperate.model_validate(
        ensure_found(
            await UserTable.set_password_and_revoke_sessions(id=id, password_hash=password_hash),
            UserError.NOT_FOUND,
        )
    )


async def disable_user(current_user: CurrentUser, target_id: str) -> UserOperate:
    target = ensure_found(await UserTable.find_detail_by_id(id=target_id), UserError.NOT_FOUND)
    _ensure_can_disable(current_user, target)
    return UserOperate.model_validate(
        ensure_found(
            await UserTable.update_by_id(id=target_id, data={"is_disabled": True}),
            UserError.NOT_FOUND,
        )
    )


async def validate_role_ids(role_ids: list[str]) -> None:
    """確認這批角色可以指派: 都存在、都沒停用、不含超級管理者角色。

    **無條件拒絕帶 `Permission.ALL` 的角色**: 超級管理者只能由 CLI 產生。
    """
    roles = await RoleTable.find_details_by_ids(role_ids)
    if len(roles) != len(set(role_ids)):
        raise LangException(404, UserError.ROLE_NOT_FOUND)
    if any(role["is_disabled"] is True for role in roles):
        raise LangException(400, UserError.ROLE_DISABLED)

    if any(Permission.ALL in role["permissions"] for role in roles):
        raise LangException(403, UserError.CANNOT_ASSIGN_SUPER_ADMIN)
