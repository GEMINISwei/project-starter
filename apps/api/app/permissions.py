"""這個專案的權限值。

enum 留在組裝層, 是為了讓 Pydantic/OpenAPI 能輸出一個穩定的字串聯集給前端: 它要是
所有啟用模組的聯集, 而只有組裝層看得到全部模組。標籤、相依展開與可否指派由引入該權限的
feature module 擁有 (manifest 的 `PermissionSpec`), 把兩者兜起來的通用邏輯在
`shared/auth/catalog.py`。
"""

from shared.auth.permissions import WILDCARD, BasePermission


class Permission(BasePermission):
    # 後台 (使用者、角色) 只開放給超級管理者, 所以不另設 `users:*`、`roles:*` 這類細粒度權限。
    # 這裡留給一般帳號要遵守的業務權限 (例如錢包), 由引入它的 module 在 `permissions.py` 宣告標籤。
    ALL = WILDCARD
