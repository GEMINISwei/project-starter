"""查詢條件的組裝輔助。

這裡**只放有呼叫端的 helper**。需要新的條件時再加，並且連同它的第一個呼叫端與測試
一起加入，避免維護未驗證的抽象。

**不要為了對稱而替每個運算子包一層。** SQLAlchemy 的運算式本身就是型別安全的
Python，`ItemTable.name.ilike(...)`、`or_(...)` 直接寫在 model 裡即可；多包一層只會
多一個要維護的名字，而且會擋住閱讀。這裡唯一的居民之所以存在，是因為它藏著一個
會咬人的細節（見下面的跳脫）。
"""

from typing import cast

from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.operators import ColumnOperators


def ilike_contains(column: ColumnOperators, keyword: str) -> ColumnElement[bool]:
    """大小寫不敏感的「包含」條件，用於 name/nickname 等關鍵字篩選。

    **一定要跳脫 `%` 與 `_`**：它們是 LIKE 的萬用字元，直接把使用者輸入拼進 pattern 會
    讓搜尋 `100%` 變成「搜尋任何以 100 開頭的字串」。跳脫字元用 `\\`，並以
    `escape=` 明確宣告 —— PostgreSQL 的預設雖然也是 `\\`，但那受 `standard_conforming_strings`
    影響，寫出來比依賴設定安全。

    """
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    # 參數型別是 `ColumnOperators`（`.ilike()` 定義在那裡，`Mapped` 欄位與純運算式都滿足它），
    # 但它宣告的回傳型別比實際寬，所以在這個唯一的出口收窄一次。
    return cast(ColumnElement[bool], column.ilike(f"%{escaped}%", escape="\\"))
