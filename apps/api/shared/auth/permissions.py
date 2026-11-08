from collections.abc import Callable, Iterable
from enum import StrEnum
from typing import Annotated, Any, TypeVar, cast

from pydantic import ValidationError, WrapValidator

#: 「擁有全部權限」的值。專案的 `Permission` enum 要有一個成員等於它 (慣例叫 `ALL`),
#: 授權檢查與權限目錄都認這個值, 不認成員名稱。
WILDCARD = "*"


class BasePermission(StrEnum):
    pass


type Dependencies[T: BasePermission] = dict[T, set[T]]


def _drop_unknown_items(value: Any, handler: Callable[[Any], Any]) -> Any:
    try:
        return handler(value)
    except ValidationError as exc:
        invalid = {
            error["loc"][0]
            for error in exc.errors()
            if error["loc"] and isinstance(error["loc"][0], int)
        }
        if not invalid or not isinstance(value, list):
            raise
        return handler([item for index, item in enumerate(value) if index not in invalid])


# 回應模型的權限清單用這個型別: 停用模組或改名權限之後, 資料庫裡的角色仍留著舊字串
# (`covers()` 同一個前提), 標成 `list[Permission]` 會在驗證時丟例外變成 500,
# 掛著那個角色的人連 `/users/me` 都拿不到, 整批進不了系統。舊字串對前端沒有意義, 濾掉即可。
# 刻意不用 `type` 敘述: 那會變成具名的型別別名, OpenAPI 多出一個 `KnownPermissions_Permission_`
# schema, 前端產生的型別跟著改名。用 TypeVar 的 Annotated 在套用時直接展開, schema 不變。
_PermissionT = TypeVar("_PermissionT", bound=BasePermission)
KnownPermissions = Annotated[list[_PermissionT], WrapValidator(_drop_unknown_items)]


class PermissionResolver[PermissionT: BasePermission]:
    def __init__(
        self,
        permissions: type[PermissionT],
        dependencies: Dependencies[PermissionT] | None = None,
    ):
        self.permissions = permissions
        self.dependencies = {} if dependencies is None else {k: v for k, v in dependencies.items()}
        self._validate()

    def _validate(self) -> None:
        if not issubclass(self.permissions, StrEnum):
            raise TypeError("permissions must be subclass of StrEnum")

        for permission, deps in self.dependencies.items():
            if not isinstance(permission, self.permissions):
                raise TypeError(f"{permission} is not valid permission")

            if not isinstance(deps, set):
                raise TypeError(f"{permission} dependencies must be set")

            for dep in deps:
                if not isinstance(dep, self.permissions):
                    raise TypeError(f"{dep} is not valid dependency")

    def expand(self, permissions: set[PermissionT]) -> set[PermissionT]:
        expanded: set[PermissionT] = set(permissions)
        stack = list(permissions)

        while stack:
            permission = stack.pop()
            for dep in self.dependencies.get(permission, set()):
                if dep not in expanded:
                    expanded.add(dep)
                    stack.append(dep)

        return expanded

    def covers(self, held: Iterable[str], requested: Iterable[str]) -> bool:
        """`held` 展開後是否涵蓋 `requested` 的每一個權限 (`WILDCARD` 涵蓋一切)。

        `requested` 不必展開: `expand()` 的結果對相依是封閉的, 只要 `requested` 本身都在
        裡面, 它們的相依也必然都在。授權「不能給出自己沒有的權限」時用它 —— 指派角色、
        編輯角色權限、操作權限比自己大的人, 都是同一個判斷。
        """
        # 不先轉成 enum: 資料庫裡可能留著已停用模組的權限字串, 轉換會丟 ValueError。
        # StrEnum 成員與同值字串相等、雜湊也相同, 所以集合運算直接成立。
        expanded: set[str] = set(self.expand(cast(set[PermissionT], set(held))))
        if WILDCARD in expanded:
            return True
        return all(item in expanded for item in requested)
