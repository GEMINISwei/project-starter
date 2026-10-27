"""錯誤訊息的語系解析。

`LangText` 有 zh/en 兩個欄位, 但真正決定使用者看到哪一份的是請求的 Accept-Language。
這條線斷掉時很安靜: 英文訊息還在程式碼裡, 只是永遠不會被選中。這裡把它釘住。

`resolve_language()` 的案例與前端 `apps/web/tests/shared/i18n/locale.test.ts` **刻意相同**:
兩邊分頭演化的話, 症狀是「UI 是中文但錯誤訊息是英文」, 而且只在特定瀏覽器設定下重現。
"""

import pytest

from shared.http.errors import (
    DEFAULT_LANGUAGE,
    BaseError,
    LangException,
    LangText,
    Language,
    current_language,
    resolve_language,
    resolve_text,
)


class SampleError(BaseError):
    NOT_FOUND = LangText(zh="找不到資料", en="Not Found")


SAMPLE_TEXT = LangText(zh="中文", en="English")


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("en", Language.EN),
        ("en-US", Language.EN),
        ("en-US,en;q=0.9", Language.EN),
        ("zh-TW,zh;q=0.9,en;q=0.8", Language.ZH),
        ("zh", Language.ZH),
        # 不支援的語言退回預設值, 而不是丟例外或回傳空字串
        ("ja-JP", DEFAULT_LANGUAGE),
        ("", DEFAULT_LANGUAGE),
        (None, DEFAULT_LANGUAGE),
    ],
)
def test_resolve_language(header, expected):
    assert resolve_language(header) == expected


def test_resolve_language_takes_first_supported_tag():
    # 只做前綴比對、不看 q 權重 (前端 resolveLocale 是同一個行為)。
    assert resolve_language("ja;q=1.0,en;q=0.1,zh;q=0.9") == Language.EN


def test_lang_exception_uses_current_language():
    token = current_language.set(Language.EN)
    try:
        assert LangException(404, SampleError.NOT_FOUND).detail == "Not Found"
    finally:
        current_language.reset(token)


def test_lang_exception_defaults_to_chinese():
    assert LangException(404, SampleError.NOT_FOUND).detail == "找不到資料"


def test_explicit_lang_argument_wins():
    token = current_language.set(Language.EN)
    try:
        assert LangException(404, SampleError.NOT_FOUND, lang="zh").detail == "找不到資料"
    finally:
        current_language.reset(token)


def test_resolve_text_follows_current_language():
    """`resolve_text()` 是「不能丟 LangException 的地方」共用的取字入口。

    使用者是從 422 驗證訊息、權限標籤、WS 事件與推播內容看到它的產出,
    而那幾處都沒有別的機制會發現語系取錯。
    """
    token = current_language.set(Language.EN)
    try:
        assert resolve_text(SAMPLE_TEXT) == "English"
    finally:
        current_language.reset(token)


def test_resolve_text_defaults_to_chinese():
    assert resolve_text(SAMPLE_TEXT) == "中文"
