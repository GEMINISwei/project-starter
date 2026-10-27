"""把 `Language` enum 交給前端的模組。

**這個端點主要是為了契約而存在** —— 前端只從產生的型別取語系聯集, 執行期幾乎不會呼叫它。
`Language` 只經由這裡進 OpenAPI (`Permission` 則隨 roles 的 schema 進去)。少了它, `Language` 不會
出現在 OpenAPI 裡, 前端的 `Locale` 就只能手抄一份, 兩邊各自飄的時候沒有任何檢查會發現。
所以看起來沒人用**不代表可以刪**。
"""

from shared.module import ModuleManifest

from .router import router

MODULE = ModuleManifest(name="languages", routers=(router,))
