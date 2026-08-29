"""權限值與彙整後的執行期目錄。

enum 留在組裝層，是為了讓 Pydantic／OpenAPI 能輸出一個穩定的字串聯集給前端。
標籤、相依展開與可否指派則由引入該權限的 feature module 擁有。

**目錄本身是「每個 app 一份」的值，不是行程層級的全域。** `create_app()` 會依它實際拿到的
modules 建一份 `PermissionCatalog` 掛到 `app.state`，需要的人從 `request.app.state` 取
（與 `current_user_resolver` 同一套做法）。改成全域會讓同一個行程裡的第二次 `create_app()`
**靜靜換掉**第一個 app 的目錄與相依展開 —— 沒有例外、沒有警告，而錯誤取決於執行順序。
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from shared.auth.permissions import BasePermission, Dependencies, PermissionResolver
from shared.http.errors import resolve_text
from shared.module import PermissionSpec


class Permission(BasePermission):
    ALL = "*"
    USER_READ = "users:read"
    USER_CREATE = "users:create"
    USER_UPDATE_OWN = "users:update:own"
    USER_UPDATE_ANY = "users:update:any"
    USER_DELETE = "users:delete"
    USER_MANAGE = "users:manage"
    ROLE_READ = "roles:read"
    ROLE_CREATE = "roles:create"
    ROLE_UPDATE = "roles:update"
    ROLE_MANAGE = "roles:manage"
    PUSH_SEND = "push:send"
    ITEM_READ = "items:read"
    ITEM_CREATE = "items:create"
    ITEM_UPDATE = "items:update"
    ITEM_DELETE = "items:delete"
    ITEM_MANAGE = "items:manage"


@dataclass(frozen=True)
class PermissionCatalog:
    """一個 app 實際啟用的權限 metadata，加上照它建出來的 resolver。

    兩者一起走：resolver 的相依關係就是從 `specs` 算出來的，分開傳遞時很容易出現
    「目錄換了但展開規則沒換」的組合。
    """

    specs: Mapping[Permission, PermissionSpec]
    resolver: PermissionResolver[Permission]

    def assignable_permissions(self) -> list[dict[str, str]]:
        return [
            {
                "value": permission.value,
                "label": resolve_text(spec.label),
            }
            for permission, spec in self.specs.items()
            if spec.assignable
        ]


def _collect(specs: Iterable[PermissionSpec]) -> dict[Permission, PermissionSpec]:
    collected: dict[Permission, PermissionSpec] = {}
    for spec in specs:
        permission = Permission(spec.value)
        if permission in collected:
            raise RuntimeError(f"duplicate permission spec: {permission.value}")
        collected[permission] = spec
    return collected


def validate_permission_coverage(specs: Iterable[PermissionSpec]) -> None:
    """確認 enum 與各 module 提供的 metadata 描述的是同一組權限。

    這是**靜態**不變條件：`Permission` 多了一個成員卻沒有任何 module 提供 metadata 時，
    權限依然存在也依然能擋 API，但不會出現在 `GET /permissions/`，也就永遠指派不出去 ——
    那是個不會有人發現的失敗。由 `app.registry` 在載入完整啟用清單時檢查。
    """
    configured = _collect(specs)
    expected = set(Permission) - {Permission.ALL}
    missing = expected - set(configured)
    extra = set(configured) - expected
    if missing or extra:
        raise RuntimeError(
            "permission metadata mismatch: "
            f"missing={sorted(item.value for item in missing)}, "
            f"extra={sorted(item.value for item in extra)}"
        )


def build_permission_catalog(specs: Iterable[PermissionSpec]) -> PermissionCatalog:
    """為某一組啟用中的 module 組出權限目錄。

    由 `create_app()` 以**它實際啟用的** modules 呼叫，所以停用一個 module 之後，
    它的權限就不會再出現在可指派清單裡。完整性由 `validate_permission_coverage`
    另外把關 —— 這裡刻意不要求完整，否則就無法用子集合組出一個 app。
    """
    configured = _collect(specs)
    if Permission.ALL in configured:
        raise RuntimeError("permission metadata mismatch: 萬用字元 '*' 不由任何 module 提供")

    dependencies: Dependencies[Permission] = {
        permission: {Permission(item) for item in spec.dependencies}
        for permission, spec in configured.items()
        if spec.dependencies
    }

    return PermissionCatalog(
        specs=configured,
        resolver=PermissionResolver(permissions=Permission, dependencies=dependencies),
    )
