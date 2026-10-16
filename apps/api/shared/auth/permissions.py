from collections.abc import Iterable
from enum import StrEnum
from typing import cast

#: 「擁有全部權限」的值。專案的 `Permission` enum 要有一個成員等於它 (慣例叫 `ALL`),
#: 授權檢查與權限目錄都認這個值, 不認成員名稱。
WILDCARD = "*"


class BasePermission(StrEnum):
    pass


type Dependencies[T: BasePermission] = dict[T, set[T]]


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
