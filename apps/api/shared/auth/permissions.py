from enum import StrEnum


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
