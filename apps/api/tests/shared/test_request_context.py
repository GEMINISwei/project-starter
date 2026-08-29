"""追蹤識別碼的清洗規則（`shared/http/context.py`）。

這個值可能來自外部 header 且會被直接寫進 log，所以「不合格就換掉」是安全要求，
不是格式潔癖 —— 帶換行的值能偽造出一整行假紀錄。
"""

from shared.http.context import (
    MAX_REQUEST_ID_LENGTH,
    current_request_id,
    new_request_id,
    resolve_request_id,
)


def test_generated_ids_are_unique_and_safe():
    first, second = new_request_id(), new_request_id()

    assert first != second
    assert resolve_request_id(first) == first


def test_valid_upstream_id_is_reused():
    assert resolve_request_id("abc-123_XYZ.4") == "abc-123_XYZ.4"


def test_missing_id_gets_a_generated_one():
    generated = resolve_request_id(None)

    assert generated and generated != "-"
    assert resolve_request_id("") != ""


def test_unsafe_ids_are_replaced():
    for unsafe in ("with space", "line\nbreak", "semi;colon", "a" * (MAX_REQUEST_ID_LENGTH + 1)):
        resolved = resolve_request_id(unsafe)
        assert resolved != unsafe
        assert resolve_request_id(resolved) == resolved


def test_default_marks_absence_of_a_request():
    """CLI 腳本與啟動流程也會寫 log，那時不在請求脈絡裡。"""
    assert current_request_id.get() == "-"
