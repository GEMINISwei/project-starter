"""後端 module manifest 的契約。

router、資料表與權限 metadata 都由 feature module 自己擁有,
組裝層只決定哪些 manifest 要啟用。

**這是契約, 不是組裝, 所以住在 `shared/`。** 它完全不認識 `ENABLED_MODULES`,
放進 `app/` 只會多出一條「module → 組裝層」的反向依賴邊, 而那條邊換不到任何東西。
驗證一組 manifest 的規則 (撞名、身分來源至多一個) 同樣與專案無關, 也住在這裡。
前端的對應檔案是 `apps/web/shared/module.ts`, 兩邊刻意對稱 ——
`modules/*/manifest.py` 只往 `shared/` 看, 組裝層單向 import 各 manifest。
"""

from collections.abc import Iterable
from dataclasses import dataclass

from fastapi import APIRouter

from shared.auth.contracts import CurrentUserResolver
from shared.auth.permissions import BasePermission
from shared.db.table import BaseTable
from shared.http.errors import LangText


@dataclass(frozen=True)
class PermissionSpec:
    """一個權限的顯示與展開規則, 由引入它的 module 提供。

    `label` 寫動作本身 (「查看」), `category` 寫它屬於哪一類 (「使用者」) —— 角色編輯畫面
    依 `category` 分組、組內只顯示 `label`。兩者都由後端提供, 前端不另外維護一份標籤,
    新增 module 時就不必回頭改角色畫面。同一個 module 的權限通常共用同一個 `category`。
    """

    value: BasePermission
    label: LangText
    category: LangText
    dependencies: frozenset[BasePermission] = frozenset()
    assignable: bool = True


@dataclass(frozen=True)
class ModuleManifest:
    name: str
    routers: tuple[APIRouter, ...] = ()
    tables: tuple[type[BaseTable], ...] = ()
    permissions: tuple[PermissionSpec, ...] = ()
    #: 以 username 取得使用者 (含展開後的 permissions) 的函式。
    #:
    #: `shared/auth` 的權限依賴需要一個「身分來源」, 但 shared 不認識任何 domain,
    #: 所以由擁有使用者資料的那個 module 從這裡提供, `create_platform_app()` 再掛到 `app.state`。
    #: 由 manifest 提供而不是讓組裝層直接 import `modules.users` ——
    #: 後者會讓組裝層認識一個具名模組, users 也就事實上不可替換、不可停用。
    #: 整個 app 至多一個 module 提供 (`resolve_current_user_resolver()` 會擋掉第二個)。
    current_user_resolver: CurrentUserResolver | None = None


def validate_modules(modules: Iterable[ModuleManifest]) -> tuple[ModuleManifest, ...]:
    """擋下撞名的 module、router prefix、資料表類別與資料表名稱。"""
    resolved = tuple(modules)
    names: set[str] = set()
    router_prefixes: set[str] = set()
    for module in resolved:
        if not module.name or module.name in names:
            raise RuntimeError(f"invalid or duplicate module name: {module.name!r}")
        names.add(module.name)
        for router in module.routers:
            if router.prefix in router_prefixes:
                raise RuntimeError(f"duplicate router prefix: {router.prefix}")
            router_prefixes.add(router.prefix)
    _validate_tables(resolved)
    return resolved


def _validate_tables(modules: tuple[ModuleManifest, ...]) -> None:
    model_names: set[str] = set()
    table_names: set[str] = set()
    for module in modules:
        for model in module.tables:
            if not issubclass(model, BaseTable):
                raise RuntimeError(f"module {module.name} registered a non-table: {model!r}")
            if model.__name__ in model_names:
                raise RuntimeError(f"duplicate table class: {model.__name__}")
            model_names.add(model.__name__)
            if model.__tablename__ in table_names:
                raise RuntimeError(f"duplicate table name: {model.__tablename__}")
            table_names.add(model.__tablename__)


def resolve_current_user_resolver(
    modules: Iterable[ModuleManifest],
) -> CurrentUserResolver | None:
    """挑出提供身分來源的那個 module。

    至多一個: 兩個 module 都提供時, 「登入的是誰」會取決於啟用清單的順序,
    而那是個不會有人發現的錯誤。沒有任何 module 提供時回傳 None —— 用一小組 module
    組出來的 app (例如只掛一條路由的測試) 本來就不需要身分來源。
    """
    providers = [module for module in modules if module.current_user_resolver is not None]
    if len(providers) > 1:
        names = ", ".join(module.name for module in providers)
        raise RuntimeError(f"multiple modules provide current_user_resolver: {names}")
    return providers[0].current_user_resolver if providers else None


def table_models(modules: Iterable[ModuleManifest]) -> list[type[BaseTable]]:
    """啟用中 module 的所有資料表, 依類別名稱排序 (seed 與 migration 的順序才穩定)。"""
    validated = validate_modules(modules)
    models = [model for module in validated for model in module.tables]
    return sorted(models, key=lambda model: model.__name__)
