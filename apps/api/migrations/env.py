"""Alembic 的執行環境。

兩件事跟 `alembic init` 產生的樣板不同, 兩件都是刻意的:

1. **連線字串從環境變數來, 不從 `alembic.ini`。** `POSTGRES_URL` 裡有密碼, 而
   `alembic.ini` 是進版控的。樣板預設讀 ini 的 `sqlalchemy.url`, 照用等於把密碼寫進
   repo —— 而且那會多出一個環境變數同步點 (見 docs/development.md〈環境變數的同步點〉)。
2. **`target_metadata` 接的是 `app.registry` 載入後的 `BaseTable.metadata`。**
   要 import `app.registry` 而不是逐一 import model: 啟用哪些 module 是組裝層的決定,
   autogenerate 要看到的是「這個 app 實際掛了哪些表」。少了這個 import, metadata 會是
   空的, 而 autogenerate 會**安靜地產出一支把所有表都 DROP 掉的 migration**。
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# import 有副作用 (把所有 model 掛上 metadata), 所以不能靠 `from … import`。
import app.registry  # noqa: F401
from shared.db.table import BaseTable

config = context.config

if config.config_file_name is not None:
    # 預設會停用所有已經存在的 logger。`scripts/db.py migrate` 在同一個行程裡接著跑 seed,
    # 應用程式的 log 會因此全部靜音, 出錯時什麼都看不到。
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = BaseTable.metadata


def _database_url() -> str:
    url = os.environ.get("POSTGRES_URL")
    if not url:
        # 訊息要講「去哪裡設」。alembic 自己的錯誤只會說連線字串是空的,
        # 看不出這個專案刻意不把它放在 ini 裡。
        raise SystemExit("需要環境變數 POSTGRES_URL（見 .env / .env.example）")
    return url


# autogenerate 的比對範圍。**兩個都要開, 而且理由不同**:
#
#   compare_type          預設就是開的, 但寫出來是因為它正是引入 Alembic 的主要理由 ——
#                         「改了既有欄位的型別卻沒寫 migration」是這個 repo 之前唯一
#                         沒有紅燈的正確性問題。
#   compare_server_default 預設**關著**。不開的話, 加/改 server default 不會被偵測到,
#                         而那類變更同樣是靜默的。它偶爾會有假陽性 (資料庫會把
#                         `'x'` 正規化成 `'x'::text`), 代價是產出的 migration 偶爾要
#                         手動刪一段 —— 那比漏掉好。
_COMPARE_OPTIONS = {
    "compare_type": True,
    "compare_server_default": True,
}


def run_migrations_offline() -> None:
    """`--sql` 模式: 不連資料庫, 把 SQL 印出來。

    用途是「要把變更交給 DBA 執行」或想先看一眼會下什麼 SQL。日常部署走 online。
    """
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **_COMPARE_OPTIONS,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, **_COMPARE_OPTIONS)

    # 一個交易包住整批。任何一支失敗就整批回滾, 不會留下「跑了一半」的結構 ——
    # PostgreSQL 的 DDL 是可交易的, 所以這個保證是真的。
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
