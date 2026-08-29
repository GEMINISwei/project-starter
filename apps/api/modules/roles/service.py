from typing import Any, Literal

from app.permissions import Permission
from shared.db.table import resolve_disabled_at
from shared.http.errors import BaseError, LangException, LangText, ensure_found

from .model import RoleTable
from .schema import RoleCreate, RoleInfo, RoleList, RoleOperate, RoleOptionList, RoleUpdate


class RoleError(BaseError):
    NOT_FOUND = LangText(zh="角色不存在", en="Role Not Found")
    CANNOT_USE_ALL_PERMISSION = LangText(
        zh="一般角色不可使用最高權限",
        en="Role Cannot Use All Permission",
    )
    CANNOT_DISABLE_DEFAULT = LangText(zh="預設角色不可停用", en="Cannot Disable Default Role")
    CANNOT_UPDATE_DEFAULT_PERMISSIONS = LangText(
        zh="預設角色不可修改權限",
        en="Cannot Update Default Role Permissions",
    )


async def create_role(form_data: RoleCreate) -> RoleOperate:
    validate_regular_permissions(form_data.permissions)
    return RoleOperate.model_validate(
        await RoleTable.create(
            data={
                **form_data.model_dump(),
                "code": None,
            }
        )
    )


async def get_role(id: str) -> RoleInfo:
    return RoleInfo.model_validate(
        ensure_found(await RoleTable.find_detail_by_id(id), RoleError.NOT_FOUND)
    )


async def get_role_list(
    limit: int,
    cursor: str | None = None,
    direction: Literal["next", "prev"] = "next",
    name: str | None = None,
    is_disabled: bool | None = None,
) -> RoleList:
    return RoleList.model_validate(
        await RoleTable.find_list(
            cursor=cursor,
            direction=direction,
            limit=limit,
            name=name,
            is_disabled=is_disabled,
        )
    )


async def get_role_options(is_disabled: bool | None = None) -> RoleOptionList:
    return RoleOptionList.model_validate(await RoleTable.find_options(is_disabled=is_disabled))


async def update_role(id: str, form_data: RoleUpdate) -> RoleOperate:
    role = ensure_found(await RoleTable.find_detail_by_id(id), RoleError.NOT_FOUND)

    # 明確標成 dict[str, Any]：下面會塞進 list[Permission] / bool / datetime，
    # 少了註記時 mypy 會從第一個鍵把它推論成 dict[str, str]。
    update_data: dict[str, Any] = {
        "name": form_data.name,
    }

    if RoleTable.is_system_role(role):
        if role["permissions"] != form_data.permissions:
            raise LangException(403, RoleError.CANNOT_UPDATE_DEFAULT_PERMISSIONS)
        if form_data.is_disabled is True:
            raise LangException(403, RoleError.CANNOT_DISABLE_DEFAULT)
    else:
        validate_regular_permissions(form_data.permissions)
        update_data["permissions"] = form_data.permissions
        update_data["is_disabled"] = form_data.is_disabled
        update_data["disabled_at"] = resolve_disabled_at(
            role["disabled_at"],
            form_data.is_disabled,
        )

    # 再包一次 ensure_found：查到之後、更新之前文件仍可能被刪掉。
    return RoleOperate.model_validate(
        ensure_found(await RoleTable.update_by_id(id=id, data=update_data), RoleError.NOT_FOUND)
    )


async def disable_role(id: str) -> RoleOperate:
    role = ensure_found(await RoleTable.find_detail_by_id(id), RoleError.NOT_FOUND)
    if RoleTable.is_system_role(role):
        raise LangException(403, RoleError.CANNOT_DISABLE_DEFAULT)

    return RoleOperate.model_validate(
        ensure_found(
            await RoleTable.update_by_id(
                id=id,
                data={
                    "is_disabled": True,
                    "disabled_at": resolve_disabled_at(role["disabled_at"], True),
                },
            ),
            RoleError.NOT_FOUND,
        )
    )


def validate_regular_permissions(permissions: list[Permission]) -> None:
    if Permission.ALL in permissions:
        raise LangException(403, RoleError.CANNOT_USE_ALL_PERMISSION)
