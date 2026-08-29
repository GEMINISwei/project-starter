"""DB 管理 CLI — seed / reset / backup / restore / migrate / create-superuser

用法：
  python scripts/db.py seed                          # 補齊缺少的 seed 資料
  python scripts/db.py reset                         # 清空所有資料表（dev only）
  python scripts/db.py backup                        # 備份到容器內的暫存目錄，路徑印在 stdout
  python scripts/db.py restore <備份檔名> < a.gz     # 從 stdin 讀 dump 還原
  python scripts/db.py migrate                       # 建表 + 執行所有未套用的 migration
  python scripts/db.py migrate --dry-run             # 只列出待執行的 migration
  python scripts/db.py create-superuser              # 互動式建立超級管理者

backup／restore 不碰主機檔案系統 —— 容器裡沒有掛任何備份目錄，主機端由
`scripts/backup.sh` / `scripts/restore.sh` 負責把檔案搬進搬出。這是為了讓
`backups/` 只在真的備份過之後才存在（bind mount 會讓 docker 在啟動時就默默建立它）。

因此 backup 是這支 CLI 唯一「**stdout 是資料**」的子指令：它只印備份檔路徑，給呼叫端接著用。
所有給人看的訊息一律走 stderr，混進 stdout 會讓呼叫端拿到一個不存在的路徑。
"""

import asyncio
import getpass
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _db_name() -> str:
    """連線字串上的資料庫名稱。

    **要從 URL 取，不能用 `PROJECT_NAME-MODE` 拼。** 資料庫名由 `POSTGRES_DB` 決定，
    它跟專案名與模式沒有任何關係，兩者可以完全不一樣 —— 拼出來的名字會讓備份檔名指向
    一個根本不存在的資料庫，而備份內容其實是另一個，而且不會有任何錯誤。
    """
    path = urlsplit(_async_url()).path.lstrip("/")
    if not path:
        raise SystemExit("POSTGRES_URL 沒有指定資料庫名稱")
    return path


def _async_url() -> str:
    return os.environ["POSTGRES_URL"]


def _libpq_url() -> str:
    """把 SQLAlchemy 的 `postgresql+asyncpg://…` 換成 pg_dump／psql 認得的 `postgresql://…`。

    只換 scheme，其餘（帳密、主機、資料庫名、query）原樣保留 —— 自己重組連線字串
    會在密碼含特殊字元時默默切錯，而症狀是「認證失敗」，看不出是解析問題。
    """
    parts = urlsplit(_async_url())
    return urlunsplit(parts._replace(scheme="postgresql"))


def _engine():
    from shared.db.session import configure_session_factory, create_engine

    engine = create_engine(_async_url())
    configure_session_factory(engine)
    return engine


# ── seed ──────────────────────────────────────────────────────────────────────


async def cmd_seed():
    from app.registry import TABLE_MODELS
    from shared.db.session import session_scope

    engine = _engine()
    try:
        async with session_scope() as session:
            for model in TABLE_MODELS:
                await model.ensure_seed(session=session)
        print("seed 完成。")
    finally:
        await engine.dispose()


# ── reset ─────────────────────────────────────────────────────────────────────


async def cmd_reset():
    if os.environ.get("MODE") != "development":
        print("錯誤：reset 只能在 MODE=development 執行")
        sys.exit(1)

    from sqlalchemy import text

    engine = _engine()
    try:
        async with engine.begin() as connection:
            # 整個 schema 砍掉重建，而不是逐張 DROP TABLE：外鍵讓刪除有順序，
            # 逐張刪要自己算拓撲排序，而那份順序會隨著新增關聯默默失效。
            # `public` 是預設 schema，migrate 會把表建回來。
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
        print("資料庫已清空。請執行 `make migrate` 重建資料表。")
    finally:
        await engine.dispose()


# ── backup ────────────────────────────────────────────────────────────────────


# 備份檔名的唯一定義。restore 要從檔名反推備份當時的 DB 名稱，
# 所以「怎麼組」與「怎麼拆」必須放在同一個地方 —— 分開寫的話，改了組法而忘了拆法，
# 症狀是還原「成功」但內容對不上，不會有任何錯誤訊息。
BACKUP_NAME_RE = re.compile(r"^backup_(?P<db>.+)_\d{8}_\d{6}\.dump$")


def cmd_backup():
    """備份到容器內的暫存目錄，並把完整路徑印在 stdout（見模組 docstring）。

    寫成檔案而不是直接串到 stdout：檔名要由這裡決定（DB 名稱只有容器裡知道），
    而備份內容與檔名沒辦法在同一條 stdout 上分開送。

    用 `--format=custom`（`-Fc`）而不是純 SQL：它本身就壓縮過，而且 `pg_restore`
    可以在還原時重排順序處理外鍵相依 —— 純 SQL dump 的還原順序是寫死在檔案裡的。
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"backup_{_db_name()}_{ts}.dump"
    dest = os.path.join(tempfile.mkdtemp(prefix="backup-"), name)
    result = subprocess.run(
        [
            "pg_dump",
            f"--dbname={_libpq_url()}",
            "--format=custom",
            "--no-owner",
            "--no-acl",
            f"--file={dest}",
        ]
    )
    if result.returncode != 0:
        sys.exit(1)
    # 成功訊息由呼叫端印（它才知道檔案最後落在主機的哪裡），這裡只交出路徑。
    print(dest)


# ── restore ───────────────────────────────────────────────────────────────────


def cmd_restore(backup_name: str):
    """從 stdin 讀備份還原。參數只是檔名，用來確認它真的是這支 CLI 產生的。

    備份走 stdin 而不是路徑：備份檔住在主機上，容器看不到它（見模組 docstring）。

    `--clean --if-exists` 先卸掉既有物件再建，所以還原是「取代」而不是「疊加」——
    少了它，還原到一個非空的資料庫會撞一堆 duplicate key 而只成功一半。
    """
    if not backup_name:
        print("用法：python scripts/db.py restore <備份檔名> < 備份檔", file=sys.stderr)
        sys.exit(1)

    matched = BACKUP_NAME_RE.match(os.path.basename(backup_name))
    if not matched:
        # 認不出來就停：這個檢查擋的是「拿別的東西當備份檔餵進來」，
        # 而 pg_restore 對格式不符的輸入只會報一句看不出原因的錯。
        print(f"無法識別的備份檔名：{backup_name}", file=sys.stderr)
        print("預期格式：backup_{db_name}_{YYYYMMDD}_{HHMMSS}.dump", file=sys.stderr)
        sys.exit(1)

    source_db = matched.group("db")
    target_db = _db_name()

    result = subprocess.run(
        [
            "pg_restore",
            f"--dbname={_libpq_url()}",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-acl",
        ],
        stdin=sys.stdin.buffer,
    )
    if result.returncode != 0:
        sys.exit(1)
    print(f"還原完成：{source_db} → {target_db}", file=sys.stderr)


# ── migrate ──────────────────────────────────────────────────────────────────


MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def cmd_migrate(dry_run: bool = False):
    """建立缺少的資料表，然後執行所有尚未套用的 migration（見 scripts/migrations/）。"""
    import app.registry  # noqa: F401 —— import 才會讓所有 model 掛上 metadata
    from shared.db.migration import (
        create_missing_tables,
        ensure_migration_table,
        run_pending,
    )
    from shared.db.table import BaseTable

    engine = _engine()
    try:
        # 一個交易包住「建表 + 全部 migration + 記錄」：中途失敗時整批回滾，
        # 不會留下「表建了一半」的狀態 —— PostgreSQL 的 DDL 是可交易的。
        async with engine.begin() as connection:
            # dry-run 不寫任何東西，所以也不建表、不建記錄表。
            if not dry_run:
                await create_missing_tables(connection, BaseTable.metadata)
                await ensure_migration_table(connection)
            elif not await _migration_table_exists(connection):
                print("尚未初始化資料庫（`_migrations` 不存在），所有 migration 都待執行。")
                return
            executed = await run_pending(connection, MIGRATIONS_DIR, dry_run=dry_run)
        if not executed:
            print("沒有待執行的 migration。")
        elif not dry_run:
            print(f"完成 {len(executed)} 個 migration。")
    finally:
        await engine.dispose()


async def _migration_table_exists(connection) -> bool:
    from sqlalchemy import text

    from shared.db.migration import MIGRATION_TABLE

    return bool(
        await connection.scalar(text("SELECT to_regclass(:name)"), {"name": MIGRATION_TABLE})
    )


# ── create-superuser ─────────────────────────────────────────────────────────


def _prompt_required(label: str) -> str:
    while True:
        value = input(label).strip()
        if value:
            return value
        print("  不可為空")


def _prompt_password() -> str:
    """用 getpass 而不是 input：密碼不該回顯在終端機上。

    也**不**從 sys.argv 取 —— 那會留在 shell history 與同機其他使用者的 `ps` 輸出裡。
    """
    while True:
        password = getpass.getpass("密碼（至少 8 字元）：")
        if not password:
            print("  不可為空")
            continue
        if password != getpass.getpass("再次輸入密碼："):
            print("  兩次輸入不一致")
            continue
        return password


async def cmd_create_superuser():
    """建立一個擁有全部權限的超級管理者。

    這是網頁 `/signup` 之外唯一的建立路徑，用途有兩個：唯一超管失聯時的救援，以及
    需要第二個超管的場景。它同時會補上 `super_admin_bootstrap` 旗標，因此執行之後
    `/signup` 一律關閉（見 `modules.users.service.create_super_admin`）。
    """
    from pydantic import ValidationError

    from modules.users.public import create_super_admin
    from modules.users.schema import SuperAdminCreate
    from shared.db.session import session_scope
    from shared.http.errors import LangException

    print("建立超級管理者（此帳號擁有全部權限）")
    nickname = _prompt_required("暱稱：")
    username = _prompt_required("帳號：")
    password = _prompt_password()

    try:
        form_data = SuperAdminCreate(username=username, nickname=nickname, password=password)
    except ValidationError as exc:
        # 只印訊息，不吐 traceback —— 這是使用者輸入錯誤，不是程式壞掉。
        for error in exc.errors():
            print(f"錯誤：{'.'.join(str(loc) for loc in error['loc'])} {error['msg']}")
        sys.exit(1)

    engine = _engine()
    try:
        async with session_scope():
            user = await create_super_admin(form_data=form_data)
    except LangException as exc:
        print(f"錯誤：{exc.detail}")
        sys.exit(1)
    finally:
        await engine.dispose()

    print(f"已建立超級管理者：{username}（id: {user.id}）")
    print("提示：`/signup` 已關閉，.env 的 REGISTER_KEY 可以清空。")


# ── 入口 ──────────────────────────────────────────────────────────────────────

COMMANDS = {
    "seed": lambda: asyncio.run(cmd_seed()),
    "reset": lambda: asyncio.run(cmd_reset()),
    "backup": cmd_backup,
    "restore": lambda: cmd_restore(sys.argv[2] if len(sys.argv) > 2 else ""),
    "migrate": lambda: asyncio.run(cmd_migrate(dry_run="--dry-run" in sys.argv)),
    "create-superuser": lambda: asyncio.run(cmd_create_superuser()),
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in COMMANDS:
        print(f"未知命令：{cmd!r}\n可用：{', '.join(COMMANDS)}")
        sys.exit(1)
    COMMANDS[cmd]()
