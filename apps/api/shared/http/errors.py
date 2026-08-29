"""雙語 HTTP 文字與例外。

`Language` 是前後端語系清單的唯一來源，透過 `/languages/` 進入 OpenAPI；前端的完整性由
產生型別與型別測試驗證。這是維護方式，不寫進 enum docstring，避免外流到公開 API 文件。
"""

from contextvars import ContextVar
from dataclasses import dataclass
from enum import Enum, StrEnum

from fastapi import HTTPException


class Language(StrEnum):
    """API 訊息支援的語系。"""

    ZH = "zh"
    EN = "en"


DEFAULT_LANGUAGE = Language.ZH

# 錯誤訊息語言。由 `app/server.py` 的 middleware 依 Accept-Language 設定。
#
# 用 ContextVar 而不是把 lang 一路當參數傳：錯誤是在 service 深處丟出來的，
# 要讓每一層都帶著 request 語言，等於把 HTTP 的概念滲透進整個商業邏輯。
# ContextVar 在 asyncio 中是每個 task 獨立的，不會有請求之間互相污染的問題。
current_language: ContextVar[Language] = ContextVar("current_language", default=DEFAULT_LANGUAGE)


def resolve_language(accept_language: str | None) -> Language:
    """從 Accept-Language header 挑出支援的語言，無法判斷時回傳預設值。

    只做前綴比對（`en-US` → `en`），不處理 q 權重 —— 這個專案只有兩種語言，
    引入完整的內容協商並不划算。前端 `resolveLocale()` 刻意是同一個行為。
    """
    if not accept_language:
        return DEFAULT_LANGUAGE

    for part in accept_language.split(","):
        tag = part.split(";")[0].strip().lower()
        primary = tag.split("-")[0]
        # StrEnum 的成員查詢用 try/except：`primary in Language` 在 3.12 之後雖然可行，
        # 但這樣寫同時完成「是不是支援的語系」與「轉成 enum 成員」兩件事。
        try:
            return Language(primary)
        except ValueError:
            continue

    return DEFAULT_LANGUAGE


@dataclass(frozen=True)
class LangText:
    zh: str
    en: str


def resolve_text(text: LangText) -> str:
    """依當前請求的語言取出字串。

    給**不能丟 LangException 的地方**用 —— pydantic 的 validator（必須丟 ValueError，
    FastAPI 才會轉成 422）、要把文字放進回應 body 的地方（權限標籤），以及會送到使用者眼前
    但不是錯誤的文案（WebSocket 事件訊息、推播內容）。

    **只有收件人就是這次請求的發起者時才能用**（ContextVar 裝的是這次請求的語系）。
    廣播給多人的內容不適用 —— 那些收件人各有各的語系，而事件只組一次。
    """
    return text.en if current_language.get() is Language.EN else text.zh


class BaseError(Enum):
    def __new__(cls, value: LangText) -> BaseError:
        if not isinstance(value, LangText):
            raise TypeError(f"{cls.__name__} value must be LangText")
        obj = object.__new__(cls)
        obj._value_ = value
        return obj


class LangException(HTTPException):
    def __init__(
        self,
        code: int,
        error: BaseError,
        lang: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        # lang 未指定時取當前請求的語言（見 current_language）。
        resolved = lang or current_language.get()
        # headers 是給「錯誤本身帶有協定語義」的情況用的，目前唯一的使用者是 429 的
        # Retry-After（見 shared/http/rate_limit.py）。沒有它，用戶端只能靠猜的重試。
        super().__init__(
            status_code=code,
            detail=error.value.en if resolved == "en" else error.value.zh,
            headers=headers,
        )


class NoChangeError(Exception):
    pass


def ensure_found[T](value: T | None, error: BaseError, status_code: int = 404) -> T:
    if value is None:
        raise LangException(status_code, error)
    return value
