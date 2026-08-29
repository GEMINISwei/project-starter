"""游標分頁的測試。

`BaseTable.get_page` 涵蓋游標編解碼、雙向翻頁、`where` 條件與 total_count 重算。
這裡分兩層：

- 游標編解碼是純函式，不需要資料庫，一律執行。
- `get_page` / `get_all` 的行為需要真的 PostgreSQL，標記為 `integration`；本機沒有
  資料庫時可用 `pytest -m "not integration"` 略過，CI 上會實際執行。
"""

import uuid
from datetime import datetime

import pytest

from shared.db.table import _decode_cursor, _encode_cursor
from shared.http.errors import LangException

# ── 游標編解碼（純函式，不需要 DB）───────────────────────────────────────────────


def test_cursor_round_trip_with_datetime():
    """datetime 型別的排序值要能原樣還原 —— get_page 預設就是用 created_at 排序。"""
    sort_value = datetime(2026, 7, 31, 12, 34, 56, 789000)
    row_id = uuid.uuid4()

    decoded_value, decoded_id = _decode_cursor(_encode_cursor(sort_value, str(row_id)))

    assert decoded_value == sort_value
    assert decoded_id == row_id


def test_cursor_round_trip_with_string():
    """非時間的排序欄位（例如 name）也要能用。"""
    row_id = uuid.uuid4()

    decoded_value, decoded_id = _decode_cursor(_encode_cursor("Alice", str(row_id)))

    assert decoded_value == "Alice"
    assert decoded_id == row_id


def test_cursor_round_trip_with_int():
    sort_value = 42
    row_id = uuid.uuid4()

    decoded_value, decoded_id = _decode_cursor(_encode_cursor(sort_value, str(row_id)))

    assert decoded_value == 42
    assert decoded_id == row_id


def test_cursor_is_opaque_base64():
    """游標對前端應該是不透明字串：不可以讓人一眼看出（或手動竄改）內部欄位。"""
    cursor = _encode_cursor(datetime(2026, 1, 1), str(uuid.uuid4()))

    assert "2026" not in cursor
    # urlsafe base64 只會用到 - 和 _，這裡確認沒有原始的日期分隔符與 UUID 的連字號。
    assert "-" not in cursor


@pytest.mark.parametrize(
    "bad_cursor",
    [
        "not-base64!!!",
        "",
        "eyJmb28iOiAiYmFyIn0=",  # 合法 base64，但內容不是 [sort_value, id]
        "W10=",  # base64 的 "[]"，解出來長度不對
    ],
)
def test_invalid_cursor_raises_400(bad_cursor):
    """壞掉或被竄改的游標要回 400，而不是 500。"""
    with pytest.raises(LangException) as exc_info:
        _decode_cursor(bad_cursor)

    assert exc_info.value.status_code == 400


def test_invalid_uuid_in_cursor_raises_400():
    """游標格式正確但 id 不是合法 UUID 時同樣要被擋成 400。"""
    forged = _encode_cursor("value", "not-a-uuid")

    with pytest.raises(LangException) as exc_info:
        _decode_cursor(forged)

    assert exc_info.value.status_code == 400


# ── get_page 翻頁行為（需要真的 PostgreSQL）─────────────────────────────────────


@pytest.mark.integration
@pytest.mark.asyncio
async def test_first_page_reports_next_but_not_previous(paged_rows):
    """第一頁：has_previous 必須是 False，has_next 必須是 True。"""
    result = await paged_rows.get_page(limit=2)

    assert [row["name"] for row in result["list_data"]] == ["row-0", "row-1"]
    assert result["has_next"] is True
    assert result["has_previous"] is False
    assert result["total_count"] == 5
    assert result["next_cursor"] is not None
    assert result["prev_cursor"] is None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_walk_forward_through_all_pages(paged_rows):
    """一路往後翻到底，每筆資料剛好出現一次、順序正確、最後一頁 has_next 為 False。"""
    seen: list[str] = []
    cursor = None

    for _ in range(10):  # 上限保護，避免測試在有 bug 時無限迴圈
        page = await paged_rows.get_page(limit=2, cursor=cursor)
        seen.extend(row["name"] for row in page["list_data"])
        if not page["has_next"]:
            break
        cursor = page["next_cursor"]

    assert seen == ["row-0", "row-1", "row-2", "row-3", "row-4"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_paging_back_returns_previous_page(paged_rows):
    """往後翻再往前翻，要回到原本那一頁 —— 這是 keyset 分頁最容易寫錯的地方。"""
    first = await paged_rows.get_page(limit=2)
    second = await paged_rows.get_page(limit=2, cursor=first["next_cursor"])

    back = await paged_rows.get_page(limit=2, cursor=second["prev_cursor"], direction="prev")

    assert [row["name"] for row in back["list_data"]] == [
        row["name"] for row in first["list_data"]
    ]
    assert back["has_previous"] is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_total_count_reflects_filter_not_page_size(paged_rows):
    """total_count 算的是「符合條件的總數」，不是這一頁的筆數。"""
    result = await paged_rows.get_page(limit=2, where=[paged_rows.group == "a"])

    assert result["total_count"] == 3  # row-0 / row-2 / row-4
    assert len(result["list_data"]) == 2


@pytest.mark.integration
@pytest.mark.asyncio
async def test_total_count_is_not_shrunk_by_the_cursor(paged_rows):
    """翻到第二頁時 total_count 仍是全部筆數。

    游標條件若不小心也套進 `COUNT(*)`，總數會隨著翻頁一路變小 —— 而前端的
    「共 N 筆」就會在使用者往後翻的時候自己減少。
    """
    first = await paged_rows.get_page(limit=2)
    second = await paged_rows.get_page(limit=2, cursor=first["next_cursor"])

    assert second["total_count"] == 5


@pytest.mark.integration
@pytest.mark.asyncio
async def test_get_all_returns_everything_without_cursors(paged_rows):
    """get_all 回傳 `{list_data, count}`，沒有任何游標欄位。"""
    result = await paged_rows.get_all()

    assert result["count"] == 5
    assert "next_cursor" not in result
    assert [row["name"] for row in result["list_data"]] == [
        "row-0",
        "row-1",
        "row-2",
        "row-3",
        "row-4",
    ]


# ── 游標的鍵必須來自 ORM 實例，不受 to_detail() 改寫影響 ────────────────────────
#
# `to_detail()` 可以任意改寫回傳 dict 的 `id`（例如列表要顯示的是關聯對象的 id）。
# 若游標直接讀回傳資料的 `id`，存進游標的就是別張表的鍵，下一頁再拿它比對本表的 `id`，
# `sort_field` 相同時的 tie-breaker 會比錯，表現為跳過或重複資料。


@pytest.fixture
def rewriting_detail(monkeypatch):
    """回傳一個 setter：讓 `to_detail()` 把 `id` / `created_at` 改寫成指定的值。"""

    def _apply(model, row_id, created_at="hijacked"):
        original = model.to_detail

        def to_detail(self):
            return {**original(self), "id": row_id, "created_at": created_at}

        monkeypatch.setattr(model, "to_detail", to_detail)

    return _apply


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cursor_survives_to_detail_rewriting_id(paged_rows, rewriting_detail):
    """`to_detail()` 把 id / created_at 蓋掉之後，游標仍然要能正確翻到下一頁。"""
    rewriting_detail(paged_rows, "hijacked")

    first = await paged_rows.get_page(limit=2)
    assert first["next_cursor"] is not None

    second = await paged_rows.get_page(limit=2, cursor=first["next_cursor"])

    assert [row["name"] for row in second["list_data"]] == ["row-2", "row-3"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_walk_all_pages_with_to_detail_rewriting_id(paged_rows, rewriting_detail):
    """整趟翻完，每筆剛好出現一次 —— 不重複也不遺漏。"""
    rewriting_detail(paged_rows, "hijacked")

    seen: list[str] = []
    cursor = None

    for _ in range(10):
        page = await paged_rows.get_page(limit=2, cursor=cursor)
        seen.extend(row["name"] for row in page["list_data"])
        if not page["has_next"]:
            break
        cursor = page["next_cursor"]

    assert seen == ["row-0", "row-1", "row-2", "row-3", "row-4"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_pagination_is_stable_when_sort_values_tie(tied_rows):
    """`created_at` 全部相同時，靠 `id` tie-breaker 仍要不重複、不遺漏地翻完。

    這是 tie-breaker 用錯 id 時最先炸掉的情境：主要排序條件無法區分任何一筆，
    整個順序完全由 `id` 的比較決定。
    """
    seen: list[str] = []
    cursor = None

    for _ in range(10):
        page = await tied_rows.get_page(limit=2, cursor=cursor)
        seen.extend(row["name"] for row in page["list_data"])
        if not page["has_next"]:
            break
        cursor = page["next_cursor"]

    assert sorted(seen) == ["tie-0", "tie-1", "tie-2", "tie-3", "tie-4"]


@pytest.mark.integration
@pytest.mark.asyncio
async def test_tied_pagination_with_foreign_id_does_not_lose_or_repeat(
    tied_rows, rewriting_detail
):
    """`id` 被 `to_detail()` 改成另一張表的合法 UUID，而排序值全部相同。

    這條路徑不會噴 400 —— 游標解得開，只是 tie-breaker 比到了錯的東西，
    表現為安靜地跳過或重複資料。這正是最難在正式環境被發現的那一種。
    """
    rewriting_detail(tied_rows, str(uuid.uuid4()))

    seen: list[str] = []
    cursor = None

    for _ in range(10):
        page = await tied_rows.get_page(limit=2, cursor=cursor)
        seen.extend(row["name"] for row in page["list_data"])
        if not page["has_next"]:
            break
        cursor = page["next_cursor"]

    assert sorted(seen) == ["tie-0", "tie-1", "tie-2", "tie-3", "tie-4"]
