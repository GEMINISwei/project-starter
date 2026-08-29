"""integration 測試的共用守衛：本機沒有 PostgreSQL 時 skip，CI 上必須 fail。

**這是「測試安靜地停止測任何東西」的防線。** 幾個 fixture 都在連不上 PostgreSQL 時
`pytest.skip`，那是本機開發需要的；但 CI 上那批測試守著整個 repo 風險最高的幾條保證 ——
`cast` 的空頭支票（`tests/modules/test_detail_contracts.py`）、游標分頁的 tie-breaker
不變條件、bootstrap 的併發與交易回滾。而 skip 的 exit code 是 0：資料庫沒起來、
連線字串打錯、等待迴圈提早放行，整批測試消失而所有燈都是綠的。

覆蓋率也當不了代理指標 —— `pyproject.toml` 的 `fail_under` 刻意訂到「本機完全沒有
PostgreSQL 也過得了」，所以 CI 從 81% 掉到 74% 一樣綠燈。

所以 CI 設 `REQUIRE_INTEGRATION=1`（見 `.github/workflows/ci.yml` 的 api job），
讓同一個情況變成 fail。
"""

import contextlib
import os

import pytest
from sqlalchemy import text


async def require_postgres(engine, url: str, what: str = "PostgreSQL") -> None:
    """連不上就 skip（本機）或 fail（CI）。連不上時會先關掉 `engine`。"""
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception as error:
        await engine.dispose()
        need = f"需要可連線的 {what}（{url}）"
        if os.environ.get("REQUIRE_INTEGRATION"):
            pytest.fail(f"{need}；REQUIRE_INTEGRATION=1 時不允許略過 —— {error!r}")
        pytest.skip(f"{need}；本機可用 `pytest -m 'not integration'` 略過")


@contextlib.contextmanager
def restore_session_factory():
    """把全域 session factory 還原成進入前的那一個。

    integration 的 fixture 會 `configure_session_factory()` 換上自己的引擎，但那是
    **行程層級**的全域值。不還原的話，這批測試跑完之後，其餘測試會拿到一個已經
    `dispose()` 掉的引擎 —— 而症狀是「單獨跑會過、整批跑會壞」。
    """
    import shared.db.session as session_module

    previous = session_module._session_factory
    try:
        yield
    finally:
        session_module._session_factory = previous
