import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    Field,
    PlainSerializer,
    StringConstraints,
    WithJsonSchema,
)

from shared.http.errors import BaseError, LangText, resolve_text

NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _to_utc_isoformat(value: datetime) -> str:
    # naive 一律當成 UTC (這個專案寫進資料庫的就是那個, 見 shared/time.utc_now);
    # 萬一真的收到 aware 的值就換算過去, 而不是把 offset 原樣送出 —— 兩種形狀混在
    # 同一個欄位上, 前端只會在其中一種上出錯。
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    # `isoformat()` 產生的是 `+00:00`, 換成 `Z`。兩者在 RFC 3339 下等價, 選 `Z` 是因為
    # 它一眼看得出「這是 UTC」, 而 `+00:00` 常被誤讀成「沒有時區資訊」。
    return aware.isoformat().replace("+00:00", "Z")


# **回應裡的時間欄位一律用這個, 不要用裸的 `datetime`。**
#
# 資料庫裡是 naive UTC (`TIMESTAMP WITHOUT TIME ZONE`, 理由見 `shared/time`), 裸的
# `datetime` 直接序列化出去就是 `"2026-09-03T00:36:56"` —— **沒有時區標記**。JavaScript 的
# `new Date()` 會把那種字串當成**瀏覽器本地時間**解析, 於是畫面上的時間整個偏掉一個時區,
# 而且不會有任何錯誤: 型別是 string、欄位有值、格式也合法, 只是時間是錯的。
#
# 這個模板目前沒有任何回應帶時間欄位, 所以**沒有**靜態檢查在守這條 —— 現在寫一支只會是
# 一份恆真的測試, 而那比沒有更糟 (同 docs/architecture.md 對 test_i18n_text_usage 的說法)。
# 守它的是 docs/extending/new-module.md〈1. 後端模組〉第 3 步那一段, 以及這裡。
# 真的長出第二、第三個時間欄位之後, 再補一支掃 response schema 的測試才有意義。
UtcDateTime = Annotated[
    datetime,
    PlainSerializer(_to_utc_isoformat, return_type=str, when_used="json"),
    # 少了這一行, `PlainSerializer` 會讓 OpenAPI 把欄位標成裸的 `string`,
    # 契約上就看不出它是時間 —— 前端產出的型別一樣是 string, 但讀 API 文件的人少了資訊。
    WithJsonSchema({"type": "string", "format": "date-time"}),
]


class SchemaError(BaseError):
    INVALID_ID = LangText(zh="無效的資料 ID", en="Invalid Data ID")


def validate_uuid(value: str) -> str:
    # 訊息走 LangText 而不是硬編中文: 這一層其他的使用者可見文字 (shared/http/errors.py 的
    # 所有錯誤訊息) 都是 LangText, 唯獨這裡是中文字串, 等於同一層有兩套慣例。
    #
    # 這裡是 pydantic 的 validator, 必須丟 ValueError 才會轉成 422 (丟 LangException
    # 會直接變成未處理的例外), 所以取的是解析後的字串, 不是丟 LangException。
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(resolve_text(SchemaError.INVALID_ID.value)) from exc
    return value


# 路由參數與請求 body 裡的 id。**維持 `str` 而不是 `uuid.UUID`** 是刻意的:
# 對外的 id 在整個專案 (含前端型別與 OpenAPI) 都是不透明字串, 換成 UUID 型別會讓
# FastAPI 把它序列化成另一種形狀, 也讓「哪一層負責驗證格式」散開。這裡只加一道
# AfterValidator, 格式不合就是 422。
UuidText = Annotated[str, AfterValidator(validate_uuid)]


class PaginatedResponse[T](BaseModel):
    """游標分頁列表的通用回應形狀, 對應 `BaseTable.get_page` 的回傳值。

    `has_next` / `has_previous` / `total_count` 刻意**沒有預設值**。`get_page` 一律會提供
    這三個欄位; 維持必填可讓回傳形狀不完整時立刻觸發 response validation, 而不會讓前端
    把缺漏誤解成 `false` / `null` 的正常分頁狀態。

    `next_cursor` / `prev_cursor` 維持選填, 因為「沒有下一頁」時它們本來就該是 None。
    """

    list_data: list[T]
    next_cursor: str | None = None
    prev_cursor: str | None = None
    has_next: bool
    has_previous: bool
    total_count: int


class SimpleListResponse[T](BaseModel):
    """非分頁列表的通用回應形狀, 對應 `BaseTable.get_all` 的回傳值。"""

    list_data: list[T]
    count: int


class PaginationParams(BaseModel):
    """列表端點共用的游標分頁 query 參數, 搭配 `Annotated[PaginationParams, Depends()]` 使用。

    這裡**只放分頁本身的參數**。篩選條件 (`name`、`is_disabled`、`role_id`…) 請由各路由
    自己宣告 `Query`, 讓每個端點的篩選條件集中在同一處。

    需要非分頁的完整清單時請用另一條路由搭配 `SimpleListResponse` (例如
    `GET /roles/options`), 不要把 `limit` 放寬成選填 —— 那會讓同一個端點依參數回傳
    兩種形狀, 而回應型別只能標其中一種。
    """

    cursor: str | None = None
    direction: Literal["next", "prev"] = "next"
    limit: int = Field(ge=1, le=100)
