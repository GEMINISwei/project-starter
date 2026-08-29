import asyncio
import secrets
from collections.abc import Mapping
from typing import Any, Literal

import bcrypt
from sqlalchemy.exc import IntegrityError

from app.permissions import Permission
from modules.roles.public import RoleTable
from shared.auth.contracts import AppEnvProtocol, CurrentUser
from shared.auth.permissions import PermissionResolver
from shared.auth.tokens import create_token
from shared.db.table import is_unique_violation, resolve_disabled_at
from shared.db.transaction import transaction
from shared.http.errors import BaseError, LangException, LangText, ensure_found

from .bootstrap_model import SUPER_ADMIN_BOOTSTRAP_KEY, SystemStateTable
from .model import UserDetail, UserTable
from .schema import (
    SignupRequest,
    SignupResponse,
    SuperAdminCreate,
    UserCreate,
    UserInfo,
    UserList,
    UserLogin,
    UserOperate,
    UserResetPassword,
    UserToken,
    UserUpdate,
)


class UserError(BaseError):
    NOT_FOUND = LangText(zh="用戶不存在", en="User Not Found")
    USERNAME_EXISTS = LangText(zh="帳號已存在", en="Username Already Exists")
    INVALID_CREDENTIALS = LangText(zh="帳號或密碼錯誤", en="Invalid Username or Password")
    REGISTER_KEY_MISMATCH = LangText(zh="系統密碼錯誤", en="Register Key Mismatch")
    BOOTSTRAP_ALREADY_COMPLETED = LangText(
        zh="系統已完成初始化，無法再次建立超級管理者",
        en="Bootstrap Already Completed",
    )
    CANNOT_DISABLE_SUPER = LangText(zh="無法停用超級管理者帳號", en="Cannot Disable Super Admin")
    CANNOT_DISABLE_SELF = LangText(zh="無法停用自己的帳號", en="Cannot Disable Self")
    CANNOT_UPDATE_OTHER = LangText(zh="無法修改其他使用者", en="Cannot Update Other User")
    ROLE_NOT_FOUND = LangText(zh="角色不存在", en="Role Not Found")
    ROLE_DISABLED = LangText(zh="角色已停用", en="Role Disabled")
    CANNOT_ASSIGN_SUPER_ADMIN = LangText(
        zh="無法指派超級管理者角色",
        en="Cannot Assign Super Admin Role",
    )


async def _apply_disable_user(
    current_user: CurrentUser,
    # target 是從 DB 查出的**任意**使用者，不是通過認證的那一位 —— 形狀比 CurrentUser 寬
    # （帶 disabled_at），所以用 users 自己的 UserDetail 而不是 shared 的 CurrentUser。
    target: UserDetail,
    resolver: PermissionResolver[Permission],
) -> UserOperate:
    """執行停用使用者，包含所有保護邏輯。target 必須是已從 DB 查出的完整 dict。"""
    if current_user["id"] == target["id"]:
        raise LangException(403, UserError.CANNOT_DISABLE_SELF)
    if Permission.ALL in get_final_permissions(target, resolver):
        raise LangException(403, UserError.CANNOT_DISABLE_SUPER)
    return UserOperate.model_validate(
        ensure_found(
            await UserTable.update_by_id(
                id=target["id"],
                data={
                    "is_disabled": True,
                    "disabled_at": resolve_disabled_at(target["disabled_at"], True),
                },
            ),
            UserError.NOT_FOUND,
        )
    )


async def create_user(form_data: UserCreate) -> UserOperate:
    """由已登入的管理者建立一般使用者。**這條路徑永遠不能建立超級管理者。**

    超級管理者只能由 bootstrap 建立；一般使用者建立流程不能繞過角色驗證。
    """
    if await UserTable.find_detail_by_username(username=form_data.username):
        raise LangException(409, UserError.USERNAME_EXISTS)

    role_ids = form_data.role_ids or []

    await validate_role_ids(role_ids=role_ids)

    try:
        return UserOperate.model_validate(
            await UserTable.create(
                data={
                    "username": form_data.username,
                    "nickname": form_data.nickname,
                    # 逐欄列出，而不是像 create_item/create_role 那樣 `**model_dump()`：使用者
                    # 資料有「不能原樣落地」的欄位（password 必須先雜湊），用展開再覆蓋的話，
                    # 日後往 UserCreate 加一個敏感欄位而忘了處理，它就直接被寫進資料庫。
                    "password": await hash_password_async(form_data.password),
                    "role_ids": role_ids,
                }
            )
        )
    except IntegrityError as exc:
        if not is_unique_violation(exc):
            raise
        raise LangException(409, UserError.USERNAME_EXISTS) from exc


async def bootstrap_available(expected_key: str) -> bool:
    """signup 這條路徑現在還開著嗎？

    兩個條件都要成立：`REGISTER_KEY` 有設定，而且還沒有人完成過 bootstrap。
    這只是給前端決定要不要顯示表單用的**提示**，真正的把關在 `signup_user`。
    """
    if not expected_key:
        return False
    return not await SystemStateTable.exists(SUPER_ADMIN_BOOTSTRAP_KEY)


async def signup_user(
    form_data: SignupRequest,
    expected_key: str,
) -> SignupResponse:
    """建立**第一個**超級管理者。整個部署生命週期內只能成功一次。

    `system_state` 的唯一約束與使用者在同一個 transaction 裡建立，因此併發請求最多只有
    一個成功；若使用者建立失敗，guard 也會一起回滾。
    """
    # 空字串檢查必須留在比對之前：`expected_key` 為空代表這條路徑整個停用（見 app/config.py 的
    # register_key），少了它，空設定值會讓「不填邀請碼」剛好通過。比對用 compare_digest 而非
    # `!=`，避免時間差洩漏。
    if not expected_key or not secrets.compare_digest(form_data.register_key, expected_key):
        raise LangException(400, UserError.REGISTER_KEY_MISMATCH)

    # 提早檢查一次。不是併發防護（真正的仲裁者是下面的唯一鍵），只是避免在明顯不會成功的
    # 請求上白算一次 bcrypt —— 否則這條端點就成了現成的 CPU 消耗器。
    if await SystemStateTable.exists(SUPER_ADMIN_BOOTSTRAP_KEY):
        raise LangException(409, UserError.BOOTSTRAP_ALREADY_COMPLETED)

    if await UserTable.find_detail_by_username(username=form_data.username):
        raise LangException(409, UserError.USERNAME_EXISTS)

    role_ids = [await RoleTable.get_super_admin_role_id()]

    # bcrypt 要在**進入 transaction 之前**算完：那 100–300ms 跟資料庫無關，放進交易裡只是讓
    # 交易多持有鎖那麼久（見 hash_password_async）。
    password_hash = await hash_password_async(form_data.password)

    try:
        async with transaction() as session:
            await SystemStateTable.create(
                data={
                    "key": SUPER_ADMIN_BOOTSTRAP_KEY,
                    "value": {"username": form_data.username},
                },
                session=session,
            )
            return SignupResponse.model_validate(
                await UserTable.create(
                    data={
                        "username": form_data.username,
                        "nickname": form_data.nickname,
                        "password": password_hash,
                        "role_ids": role_ids,
                    },
                    session=session,
                )
            )
    except IntegrityError as exc:
        if not is_unique_violation(exc):
            raise
        # 撞到唯一約束的可能有兩個：bootstrap guard（有人比我們快一步）或 username。不去解析
        # exc 的約束名稱（那是 schema 的實作細節，改個索引名就會變），改成重新查一次狀態。
        if await SystemStateTable.exists(SUPER_ADMIN_BOOTSTRAP_KEY):
            raise LangException(409, UserError.BOOTSTRAP_ALREADY_COMPLETED) from exc
        raise LangException(409, UserError.USERNAME_EXISTS) from exc


async def create_super_admin(form_data: SuperAdminCreate) -> UserOperate:
    """由 CLI 建立超級管理者（見 `scripts/db.py create-superuser`）。

    **這個函式刻意不接在任何 router 上，也不應該接。** 它是唯一繞過
    `validate_role_ids`（那裡無條件拒絕 `Permission.ALL`）的路徑，而它的授權模型是
    「呼叫者已經有伺服器的 shell 存取權」—— 那個權限本來就大於系統內任何帳號。
    一旦把它接上 HTTP，授權模型就換成了「某個 permission」，那是完全不同的一件事。

    與 `signup_user` 的兩個差別：

    - 沒有 latch 檢查，所以可以建立第二、第三個超級管理者（救援與多管理者場景）。
    - 反過來，它會**補寫** latch。用 CLI 建立了第一個超級管理者卻不落 latch 的話，
      `/signup` 會一直開著，等於留了一條公開的建號路徑。
    """
    if await UserTable.find_detail_by_username(username=form_data.username):
        raise LangException(409, UserError.USERNAME_EXISTS)

    role_ids = [await RoleTable.get_super_admin_role_id()]

    # 同 signup_user：bcrypt 要在進入 transaction 之前算完。
    password_hash = await hash_password_async(form_data.password)

    try:
        async with transaction() as session:
            if not await SystemStateTable.exists(SUPER_ADMIN_BOOTSTRAP_KEY, session=session):
                await SystemStateTable.create(
                    data={
                        "key": SUPER_ADMIN_BOOTSTRAP_KEY,
                        "value": {"username": form_data.username},
                    },
                    session=session,
                )
            return UserOperate.model_validate(
                await UserTable.create(
                    data={
                        "username": form_data.username,
                        "nickname": form_data.nickname,
                        "password": password_hash,
                        "role_ids": role_ids,
                    },
                    session=session,
                )
            )
    except IntegrityError as exc:
        if not is_unique_violation(exc):
            raise
        # CLI 是序列執行的，只可能撞到 username（前面那次查詢與這裡之間，另一個管道建立了同名
        # 帳號）。latch 撞號由上面的 exists 檢查擋掉。
        raise LangException(409, UserError.USERNAME_EXISTS) from exc


async def login_user(form_data: UserLogin, env: AppEnvProtocol) -> UserToken:
    user_data = await UserTable.find_detail_by_username(
        username=form_data.username,
        include_password=True,
    )
    hashed_password = _DUMMY_PASSWORD_HASH if user_data is None else user_data["password"]
    # 帳號不存在時也要做一次完整的雜湊比對（用 dummy hash），否則「回應很快」本身就洩漏了帳號
    # 不存在。dummy 比對同樣要進執行緒，否則兩條路徑的耗時特徵又會不一樣。
    password_matched = await verify_password_async(
        plain_password=form_data.password, hashed_password=hashed_password
    )
    if user_data is None or user_data.get("is_disabled") is True or not password_matched:
        raise LangException(401, UserError.INVALID_CREDENTIALS)

    return UserToken.model_validate(create_token(user_data, env))


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


async def update_user_profile(
    current_user: CurrentUser,
    id: str,
    form_data: UserUpdate,
    resolver: PermissionResolver[Permission],
) -> UserOperate:
    current_permissions = get_final_permissions(current_user, resolver)
    is_self = current_user["id"] == id
    can_update_any = (
        Permission.ALL in current_permissions
        or Permission.USER_UPDATE_ANY in current_permissions
    )

    if not is_self and not can_update_any:
        raise LangException(403, UserError.CANNOT_UPDATE_OTHER)

    # 先確認目標存在：少了這一步，不存在的 id 會一路走到 `update_by_id` 回傳 None，再撞上
    # response_model 的必填 `id` 變成 500，而「查無此人」應該是 404。順帶讓下面的停用分支
    # 複用這筆資料，不必再查一次。
    target = ensure_found(await UserTable.find_detail_by_id(id), UserError.NOT_FOUND)

    # 標成 dict[str, Any]：下面會塞 list[str] / bool / datetime，
    # 少了註記時 mypy 會從第一個鍵推論成 dict[str, str]。
    update_data: dict[str, Any] = {
        "nickname": form_data.nickname,
    }

    if form_data.role_ids is not None:
        if not can_update_any:
            raise LangException(403, UserError.CANNOT_UPDATE_OTHER)
        await validate_role_ids(role_ids=form_data.role_ids)
        update_data["role_ids"] = form_data.role_ids

    if form_data.is_disabled is True:
        if is_self:
            raise LangException(403, UserError.CANNOT_DISABLE_SELF)
        if Permission.ALL in get_final_permissions(target, resolver):
            raise LangException(403, UserError.CANNOT_DISABLE_SUPER)
        update_data["is_disabled"] = True
        update_data["disabled_at"] = resolve_disabled_at(target["disabled_at"], True)
    elif form_data.is_disabled is False and can_update_any:
        update_data["is_disabled"] = False
        update_data["disabled_at"] = None

    # 再包一次 ensure_found：查到之後、更新之前文件仍可能被刪掉。
    return UserOperate.model_validate(
        ensure_found(await UserTable.update_by_id(id=id, data=update_data), UserError.NOT_FOUND)
    )


async def reset_user_password(id: str, form_data: UserResetPassword) -> UserOperate:
    # 同 update_user_profile：不存在的 id 若不在這裡擋下，會變成 500 而不是 404。
    ensure_found(await UserTable.find_detail_by_id(id), UserError.NOT_FOUND)

    password_hash = await hash_password_async(form_data.password)

    # 換密碼的同時把 auth_version +1，讓這個人所有既有的 session token 與 WS ticket
    # 立刻失效。
    return UserOperate.model_validate(
        ensure_found(
            await UserTable.set_password_and_revoke_sessions(id=id, password_hash=password_hash),
            UserError.NOT_FOUND,
        )
    )


async def disable_user(
    current_user: CurrentUser,
    target_id: str,
    resolver: PermissionResolver[Permission],
) -> UserOperate:
    target = ensure_found(await UserTable.find_detail_by_id(id=target_id), UserError.NOT_FOUND)
    return await _apply_disable_user(current_user=current_user, target=target, resolver=resolver)


async def validate_role_ids(role_ids: list[str]) -> None:
    """確認這批角色可以被指派：都存在、都沒停用、且不含超級管理者角色。

    **這個函式無條件拒絕帶 `Permission.ALL` 的角色。** 唯一能產生超級管理者的路徑是
    一次性的 bootstrap（見 `signup_user`）。若需限制操作者可指派的範圍，應另行實作並
    為該規則建立測試。
    """
    roles = await RoleTable.find_details_by_ids(role_ids)
    if len(roles) != len(set(role_ids)):
        raise LangException(404, UserError.ROLE_NOT_FOUND)
    if any(role["is_disabled"] is True for role in roles):
        raise LangException(400, UserError.ROLE_DISABLED)

    if any(Permission.ALL in role["permissions"] for role in roles):
        raise LangException(403, UserError.CANNOT_ASSIGN_SUPER_ADMIN)


def hash_password(raw_password: str) -> str:
    """**同步**版本，只給啟動時建立 dummy hash 用（見 `_DUMMY_PASSWORD_HASH`）。

    請求路徑上一律用 `hash_password_async`。
    """
    return bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """**同步**版本。請求路徑上一律用 `verify_password_async`。"""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


# bcrypt 刻意設計成慢的（那正是它抵抗暴力破解的方式），預設成本下一次雜湊約 100–300ms，而且是
# **純 CPU 工作**——直接在 async 函式裡呼叫等於把整個 event loop 停住那麼久，不是「這個請求變
# 慢」，是**所有**請求都停住。asyncio.to_thread() 丟到執行緒池，bcrypt 雜湊期間會釋放 GIL，
# 所以這裡是真的平行。
async def hash_password_async(raw_password: str) -> str:
    return await asyncio.to_thread(hash_password, raw_password)


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)


def get_final_permissions(
    user_data: Mapping[str, Any],
    resolver: PermissionResolver[Permission],
) -> set[Permission]:
    """把使用者持有的權限展開成含相依的完整集合。

    resolver 由呼叫端從 `request.app.state.permission_resolver` 傳進來，而不是 import 一份
    全域 —— 相依關係是「這個 app 啟用了哪些 module」算出來的（見 app/permissions.py）。
    """
    return resolver.expand(set(user_data.get("permissions", [])))


_DUMMY_PASSWORD_HASH = hash_password("dummy-password")
