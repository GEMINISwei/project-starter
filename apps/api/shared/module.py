"""後端 module manifest 的契約。

router、資料表與權限 metadata 都由 feature module 自己擁有，
組裝層只決定哪些 manifest 要啟用。

**這是契約，不是組裝，所以住在 `shared/`。** 它完全不認識 `ENABLED_MODULES`，
放進 `app/` 只會多出一條「module → 組裝層」的反向依賴邊，而那條邊換不到任何東西。
前端的對應檔案是 `apps/web/shared/module.ts`，兩邊刻意對稱 ——
`modules/*/manifest.py` 只往 `shared/` 看，組裝層單向 import 各 manifest。
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import APIRouter

from shared.auth.contracts import CurrentUserResolver
from shared.auth.permissions import BasePermission
from shared.db.table import BaseTable
from shared.http.errors import LangText


@dataclass(frozen=True)
class PermissionSpec:
    value: BasePermission
    label: LangText
    dependencies: frozenset[BasePermission] = frozenset()
    assignable: bool = True


@dataclass(frozen=True)
class ModuleManifest:
    name: str
    routers: tuple[APIRouter, ...] = ()
    tables: tuple[type[BaseTable], ...] = ()
    permissions: tuple[PermissionSpec, ...] = ()
    configure: Callable[[Any], None] | None = None
    #: 以 username 取得使用者（含展開後的 permissions）的函式。
    #:
    #: `shared/auth` 的權限依賴需要一個「身分來源」，但 shared 不認識任何 domain，
    #: 所以由擁有使用者資料的那個 module 從這裡提供，`create_app()` 再掛到 `app.state`。
    #: 由 manifest 提供而不是讓 `app/server.py` 直接 import `modules.users` ——
    #: 後者會讓組裝層認識一個具名模組，users 也就事實上不可替換、不可停用。
    #: 整個 app 至多一個 module 提供（`create_app()` 會擋掉第二個）。
    current_user_resolver: CurrentUserResolver | None = None
