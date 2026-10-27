"""資料庫 CLI (`scripts/db.py`)。

`migrate` 是 compose 的 migrate 服務跑的那一支, `make start` 先單獨跑它、成功才切換服務。
初始資料 (seed) 也在這一步寫入, 失敗時才會被同一道保護擋下 (見 docs/extending.md〈初始資料〉)。

用獨立的資料庫而不是 integration 共用的那一個: 其他測試會在共用的資料庫裡 `create_all`,
`alembic upgrade` 碰到已經存在的表會直接失敗。
"""

import os
from collections.abc import AsyncIterator
from urllib.parse import urlsplit, urlunsplit

import pytest
import pytest_asyncio
from sqlalchemy import text

from shared.db.session import create_engine
from tests.integration import require_postgres, restore_session_factory

DATABASE = "test_db_cli_migrate"


def _with_database(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{database}"))


@pytest_asyncio.fixture
async def migrate_url() -> AsyncIterator[str]:
    """一個全新、空的資料庫, 測完刪掉。"""
    url = os.environ.get("POSTGRES_URL", "")
    admin = create_engine(url)
    await require_postgres(admin, url)
    autocommit = admin.execution_options(isolation_level="AUTOCOMMIT")

    async with autocommit.connect() as connection:
        await connection.execute(text(f"DROP DATABASE IF EXISTS {DATABASE} WITH (FORCE)"))
        await connection.execute(text(f"CREATE DATABASE {DATABASE}"))
    try:
        yield _with_database(url, DATABASE)
    finally:
        async with autocommit.connect() as connection:
            await connection.execute(text(f"DROP DATABASE IF EXISTS {DATABASE} WITH (FORCE)"))
        await admin.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_migrate_writes_seed_data(migrate_url: str, monkeypatch: pytest.MonkeyPatch):
    from scripts import db

    monkeypatch.setenv("POSTGRES_URL", migrate_url)

    # alembic 的 env.py 與 seed 都用 asyncio.run, 不能在這個測試的事件迴圈裡直接呼叫。
    import asyncio

    with restore_session_factory():
        await asyncio.to_thread(db.cmd_migrate)

    engine = create_engine(migrate_url)
    try:
        async with engine.connect() as connection:
            codes = (await connection.execute(text("SELECT code FROM roles"))).scalars().all()
    finally:
        await engine.dispose()

    assert "super_admin" in codes
