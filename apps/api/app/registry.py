"""明列啟用中 module 的註冊表。

啟用哪些 feature 只有這一個組裝點。router 與資料表由 feature 自己擁有，
組裝層負責驗證與接線。
"""

from collections.abc import Iterable

from app.permissions import validate_permission_coverage
from modules.items.manifest import MODULE as ITEMS_MODULE
from modules.languages.manifest import MODULE as LANGUAGES_MODULE
from modules.permissions.manifest import MODULE as PERMISSIONS_MODULE
from modules.push.manifest import MODULE as PUSH_MODULE
from modules.realtime.manifest import MODULE as REALTIME_MODULE
from modules.roles.manifest import MODULE as ROLES_MODULE
from modules.users.manifest import MODULE as USERS_MODULE
from shared.auth.contracts import CurrentUserResolver
from shared.db.table import BaseTable
from shared.module import ModuleManifest

ENABLED_MODULES: tuple[ModuleManifest, ...] = (
    USERS_MODULE,
    ROLES_MODULE,
    PERMISSIONS_MODULE,
    LANGUAGES_MODULE,
    PUSH_MODULE,
    REALTIME_MODULE,
    ITEMS_MODULE,
)


def validate_modules(modules: Iterable[ModuleManifest]) -> tuple[ModuleManifest, ...]:
    resolved = tuple(modules)
    names: set[str] = set()
    router_prefixes: set[str] = set()
    model_names: set[str] = set()
    table_names: set[str] = set()

    for module in resolved:
        if not module.name or module.name in names:
            raise RuntimeError(f"invalid or duplicate module name: {module.name!r}")
        names.add(module.name)

        for router in module.routers:
            if router.prefix in router_prefixes:
                raise RuntimeError(f"duplicate router prefix: {router.prefix}")
            router_prefixes.add(router.prefix)

        for model in module.tables:
            if not issubclass(model, BaseTable):
                raise RuntimeError(f"module {module.name} registered a non-table: {model!r}")
            if model.__name__ in model_names:
                raise RuntimeError(f"duplicate table class: {model.__name__}")
            model_names.add(model.__name__)

            table_name = model.__tablename__
            if table_name in table_names:
                raise RuntimeError(f"duplicate table name: {table_name}")
            table_names.add(table_name)

    return resolved


def resolve_current_user_resolver(modules: Iterable[ModuleManifest]) -> CurrentUserResolver | None:
    """挑出提供身分來源的那個 module。

    至多一個：兩個 module 都提供時，「登入的是誰」會取決於啟用清單的順序，
    而那是個不會有人發現的錯誤。沒有任何 module 提供時回傳 None —— 用一小組 module
    組出來的 app（例如只掛一條路由的測試）本來就不需要身分來源。
    """
    providers = [module for module in modules if module.current_user_resolver is not None]
    if len(providers) > 1:
        names = ", ".join(module.name for module in providers)
        raise RuntimeError(f"multiple modules provide current_user_resolver: {names}")

    return providers[0].current_user_resolver if providers else None


def table_models(modules: Iterable[ModuleManifest]) -> list[type[BaseTable]]:
    validated = validate_modules(modules)
    models = [model for module in validated for model in module.tables]
    return sorted(models, key=lambda model: model.__name__)


ENABLED_MODULES = validate_modules(ENABLED_MODULES)
TABLE_MODELS = table_models(ENABLED_MODULES)
# 載入時只做**驗證**，不安裝任何狀態：完整啟用清單必須剛好覆蓋 `Permission` enum。
# 執行期的權限目錄由 `create_app()` 依它實際啟用的 modules 安裝（見 app.permissions）。
validate_permission_coverage(spec for module in ENABLED_MODULES for spec in module.permissions)
