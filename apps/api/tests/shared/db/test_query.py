"""`ilike_contains` 的跳脫要在真的 PostgreSQL 上驗: `%` 與 `_` 的語意是資料庫決定的。"""

import pytest

from shared.db.query import ilike_contains

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_ilike_contains_matches_percent_and_underscore_literally(empty_paged_rows):
    table = empty_paged_rows
    for name in ["100%", "1000", "a_b", "axb", "Back\\Slash", "backslash"]:
        await table.create(data={"name": name, "group": "a"})

    async def names(keyword: str) -> list[str]:
        result = await table.get_all(where=[ilike_contains(table.name, keyword)])
        return sorted(row["name"] for row in result["list_data"])

    assert await names("100%") == ["100%"]
    assert await names("a_b") == ["a_b"]
    assert await names("\\") == ["Back\\Slash"]
    # 大小寫不敏感是這個 helper 的另一半約定。
    assert await names("BACK") == ["Back\\Slash", "backslash"]
