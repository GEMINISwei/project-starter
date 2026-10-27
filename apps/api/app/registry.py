"""明列啟用中 module 的註冊表。

啟用哪些 feature 只有這一個組裝點。router 與資料表由 feature 自己擁有,
驗證規則在 `shared/module.py`, 這裡只決定清單。
"""

from app.permissions import Permission
from modules.languages.manifest import MODULE as LANGUAGES_MODULE
from modules.roles.manifest import MODULE as ROLES_MODULE
from modules.users.manifest import MODULE as USERS_MODULE
from shared.auth.catalog import validate_permission_coverage
from shared.module import ModuleManifest, table_models, validate_modules

ENABLED_MODULES: tuple[ModuleManifest, ...] = validate_modules(
    (
        USERS_MODULE,
        ROLES_MODULE,
        LANGUAGES_MODULE,
    )
)

TABLE_MODELS = table_models(ENABLED_MODULES)

# 載入時只做**驗證**, 不安裝任何狀態: 完整啟用清單必須剛好覆蓋 `Permission` enum。
# 執行期的權限目錄由 `create_app()` 依它實際啟用的 modules 安裝 (見 shared/auth/catalog.py)。
validate_permission_coverage(
    Permission, (spec for module in ENABLED_MODULES for spec in module.permissions)
)
