"""`BaseTable.ensure_seed` 的行為。

**為什麼值得測**：這段程式碼每次服務啟動都會跑（`app/server.py` 的 lifespan 與
`python scripts/db.py seed`），而且是模板把**新增的權限補到既有環境**的唯一途徑
（`modules/roles/model.py` 的 `RoleTable` 就靠它）。兩條分岔（有沒有 `seed_match_key`）、
`prepare_seed_item` hook 與一個 `raise` 分支，少了測試就只有 docstring 在守。

語義見 docs/extending.md 的「初始資料（Seed）」。
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_no_seed_data_is_a_noop(seed_row):
    model, rows = seed_row
    model.seed_data = []

    await model.ensure_seed()

    assert await rows() == []


# --- 沒有 seed_match_key：只在空資料表時整批 insert -------------------------


async def test_inserts_everything_when_table_is_empty(seed_row):
    model, rows = seed_row
    model.seed_match_key = None
    model.seed_data = [{"code": "a", "label": "A"}, {"code": "b", "label": "B"}]

    await model.ensure_seed()

    assert {row.code for row in await rows()} == {"a", "b"}


async def test_does_not_touch_a_non_empty_table(seed_row):
    """**不是** upsert：既有資料一個字都不能動，即使 seed 的內容已經改了。

    這正是兩條分岔的分界 —— 沒設 match key 就代表「這批資料只負責開機第一次」。
    """
    model, rows = seed_row
    model.seed_match_key = None
    model.seed_data = [{"code": "a", "label": "舊的"}]
    await model.ensure_seed()

    model.seed_data = [{"code": "a", "label": "新的"}, {"code": "b", "label": "B"}]
    await model.ensure_seed()

    current = await rows()
    assert len(current) == 1
    assert current[0].label == "舊的"


# --- 有 seed_match_key：每次都逐筆 upsert ----------------------------------


async def test_upserts_by_match_key(seed_row):
    model, rows = seed_row
    model.seed_match_key = "code"
    model.seed_data = [{"code": "a", "label": "A"}]

    await model.ensure_seed()

    assert len(await rows()) == 1


async def test_upsert_updates_existing_rows_without_duplicating(seed_row):
    """日後新增欄位時，已經跑起來的環境要補得到 —— 這是 match key 那條分岔存在的理由。"""
    model, rows = seed_row
    model.seed_match_key = "code"
    model.seed_data = [{"code": "a", "label": "舊的"}]
    await model.ensure_seed()

    model.seed_data = [{"code": "a", "label": "新的"}]
    await model.ensure_seed()

    current = await rows()
    assert len(current) == 1
    assert current[0].label == "新的"


async def test_upsert_keeps_the_original_created_at(seed_row):
    """`created_at` 不進 `ON CONFLICT` 的 SET 子句：重跑 seed 不可以把建立時間往後推。"""
    model, rows = seed_row
    model.seed_match_key = "code"
    model.seed_data = [{"code": "a", "label": "A"}]
    await model.ensure_seed()
    first = (await rows())[0].created_at

    model.seed_data = [{"code": "a", "label": "B"}]
    await model.ensure_seed()

    assert (await rows())[0].created_at == first


async def test_missing_match_key_fails_loudly(seed_row):
    """少了 match key 的那一筆無從判斷衝突 —— 必須當場失敗，而不是多插一筆。"""
    model, _ = seed_row
    model.seed_match_key = "code"
    model.seed_data = [{"label": "沒有 code"}]

    with pytest.raises(ValueError, match="seed item missing match key"):
        await model.ensure_seed()


# --- prepare_seed_item ------------------------------------------------------


async def test_prepare_seed_item_runs_before_writing(seed_row, monkeypatch):
    """`RoleTable` 靠這個 hook 把權限清單展開，所以它必須在寫入之前生效。"""
    model, rows = seed_row
    model.seed_match_key = "code"
    model.seed_data = [{"code": "a", "label": "原本"}]

    async def prepare(cls, item: dict) -> dict:
        return {**item, "label": "改過"}

    monkeypatch.setattr(model, "prepare_seed_item", classmethod(prepare))

    await model.ensure_seed()

    assert (await rows())[0].label == "改過"
