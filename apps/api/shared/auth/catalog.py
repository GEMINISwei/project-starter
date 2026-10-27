"""權限值與彙整後的執行期目錄。

權限的**值** (`Permission` enum) 由專案的組裝層定義: 它要是所有模組的聯集, 才能以一個
穩定的字串聯集進 OpenAPI。標籤、相依展開與可否指派則由引入該權限的 feature module 擁有
(manifest 的 `PermissionSpec`)。這裡只放把兩者兜起來的通用邏輯, enum 型別由呼叫端傳入。

**目錄本身是「每個 app 一份」的值, 不是行程層級的全域。** `create_platform_app()` 會依它
實際拿到的 modules 建一份 `PermissionCatalog` 掛到 `app.state`, 需要的人從
`request.app.state` 取 (與 `current_user_resolver` 同一套做法)。改成全域會讓同一個行程裡的
第二次建 app **靜靜換掉**第一個 app 的目錄與相依展開 —— 沒有例外、沒有警告, 而錯誤取決於
執行順序。
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from shared.http.errors import resolve_text
from shared.module import PermissionSpec

from .permissions import WILDCARD, BasePermission, Dependencies, PermissionResolver


@dataclass(frozen=True)
class PermissionCatalog[PermissionT: BasePermission]:
    """一個 app 實際啟用的權限 metadata, 加上照它建出來的 resolver。

    兩者一起走: resolver 的相依關係就是從 `specs` 算出來的, 分開傳遞時很容易出現
    「目錄換了但展開規則沒換」的組合。
    """

    specs: Mapping[PermissionT, PermissionSpec]
    resolver: PermissionResolver[PermissionT]

    def assignable_permissions(self) -> list[dict[str, str]]:
        """可指派的權限, 依 module 的宣告順序 (畫面據此分組與排列)。"""
        return [
            {
                "value": permission.value,
                "label": resolve_text(spec.label),
                "category": resolve_text(spec.category),
            }
            for permission, spec in self.specs.items()
            if spec.assignable
        ]


def _collect[PermissionT: BasePermission](
    permissions: type[PermissionT], specs: Iterable[PermissionSpec]
) -> dict[PermissionT, PermissionSpec]:
    collected: dict[PermissionT, PermissionSpec] = {}
    for spec in specs:
        permission = permissions(spec.value)
        if permission in collected:
            raise RuntimeError(f"duplicate permission spec: {permission.value}")
        collected[permission] = spec
    return collected


def validate_permission_coverage(
    permissions: type[BasePermission], specs: Iterable[PermissionSpec]
) -> None:
    """確認 enum 與各 module 提供的 metadata 描述的是同一組權限。

    這是**靜態**不變條件: enum 多了一個成員卻沒有任何 module 提供 metadata 時,
    權限依然存在也依然能擋 API, 但不會出現在可指派清單裡, 也就永遠指派不出去 ——
    那是個不會有人發現的失敗。由組裝層在載入完整啟用清單時呼叫。
    """
    configured = _collect(permissions, specs)
    expected = {permission for permission in permissions if permission.value != WILDCARD}
    missing = expected - set(configured)
    extra = set(configured) - expected
    if missing or extra:
        raise RuntimeError(
            "permission metadata mismatch: "
            f"missing={sorted(item.value for item in missing)}, "
            f"extra={sorted(item.value for item in extra)}"
        )


def build_permission_catalog[PermissionT: BasePermission](
    permissions: type[PermissionT], specs: Iterable[PermissionSpec]
) -> PermissionCatalog[PermissionT]:
    """為某一組啟用中的 module 組出權限目錄。

    以**實際啟用的** modules 呼叫, 所以停用一個 module 之後, 它的權限就不會再出現在
    可指派清單裡。完整性由 `validate_permission_coverage` 另外把關 —— 這裡刻意不要求完整,
    否則就無法用子集合組出一個 app。
    """
    configured = _collect(permissions, specs)
    if any(permission.value == WILDCARD for permission in configured):
        raise RuntimeError("permission metadata mismatch: 萬用字元 '*' 不由任何 module 提供")

    dependencies: Dependencies[PermissionT] = {
        permission: {permissions(item) for item in spec.dependencies}
        for permission, spec in configured.items()
        if spec.dependencies
    }
    return PermissionCatalog(
        specs=configured,
        resolver=PermissionResolver(permissions=permissions, dependencies=dependencies),
    )
