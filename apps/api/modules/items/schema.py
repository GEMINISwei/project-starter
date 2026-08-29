"""**範例模組**的 API 契約。用不到時整包刪除，見 docs/architecture.md「移除 module」。"""

from pydantic import BaseModel

from shared.http.schema import NonEmptyText, PaginatedResponse
from shared.http.schema import UuidText as UuidText


class ItemCreate(BaseModel):
    # NonEmptyText 會去掉前後空白並擋下空字串 —— 不要用裸 `str`，
    # 否則「只打了幾個空白」會被當成合法名稱存進資料庫。
    name: NonEmptyText
    description: str = ""


class ItemUpdate(BaseModel):
    name: NonEmptyText
    description: str = ""
    is_disabled: bool


class ItemOperate(BaseModel):
    id: str


class ItemInfo(BaseModel):
    id: str
    name: str
    description: str
    is_disabled: bool
    # 由 `ItemPipeline.with_creator()` 的 $lookup 補上，不是資料表的欄位。
    created_by_nickname: str = ""


class ItemList(PaginatedResponse["ItemInfo"]):
    pass
