import uuid
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, StringConstraints

from shared.http.errors import BaseError, LangText, resolve_text

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SchemaError(BaseError):
    INVALID_ID = LangText(zh="無效的資料 ID", en="Invalid Data ID")


def validate_uuid(value: str) -> str:
    # 訊息走 LangText 而不是硬編中文：這一層其他的使用者可見文字（shared/http/errors.py 的
    # 所有錯誤訊息）都是 LangText，唯獨這裡是中文字串，等於同一層有兩套慣例。
    #
    # 這裡是 pydantic 的 validator，必須丟 ValueError 才會轉成 422（丟 LangException
    # 會直接變成未處理的例外），所以取的是解析後的字串，不是丟 LangException。
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(resolve_text(SchemaError.INVALID_ID.value)) from exc
    return value


# 路由參數與請求 body 裡的 id。**維持 `str` 而不是 `uuid.UUID`** 是刻意的：
# 對外的 id 在整個專案（含前端型別與 OpenAPI）都是不透明字串，換成 UUID 型別會讓
# FastAPI 把它序列化成另一種形狀，也讓「哪一層負責驗證格式」散開。這裡只加一道
# AfterValidator，格式不合就是 422。
UuidText = Annotated[str, AfterValidator(validate_uuid)]


class PaginatedResponse[T](BaseModel):
    """游標分頁列表的通用回應形狀，對應 `BaseTable.get_page` 的回傳值。

    `has_next` / `has_previous` / `total_count` 刻意**沒有預設值**。`get_page` 一律會提供
    這三個欄位；維持必填可讓回傳形狀不完整時立刻觸發 response validation，而不會讓前端
    把缺漏誤解成 `false` / `null` 的正常分頁狀態。

    `next_cursor` / `prev_cursor` 維持選填，因為「沒有下一頁」時它們本來就該是 None。
    """

    list_data: list[T]
    next_cursor: str | None = None
    prev_cursor: str | None = None
    has_next: bool
    has_previous: bool
    total_count: int


class SimpleListResponse[T](BaseModel):
    """非分頁列表的通用回應形狀，對應 `BaseTable.get_all` 的回傳值。"""

    list_data: list[T]
    count: int


class PaginationParams(BaseModel):
    """列表端點共用的游標分頁 query 參數，搭配 `Annotated[PaginationParams, Depends()]` 使用。

    這裡**只放分頁本身的參數**。篩選條件（`name`、`is_disabled`、`role_id`…）請由各路由
    自己宣告 `Query`，讓每個端點的篩選條件集中在同一處。

    需要非分頁的完整清單時請用另一條路由搭配 `SimpleListResponse`（例如
    `GET /roles/options`），不要把 `limit` 放寬成選填 —— 那會讓同一個端點依參數回傳
    兩種形狀，而回應型別只能標其中一種。
    """

    cursor: str | None = None
    direction: Literal["next", "prev"] = "next"
    limit: int = Field(ge=1, le=100)
