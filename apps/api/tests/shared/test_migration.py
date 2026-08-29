"""版本化 migration 執行器的行為保證（見 `shared/db/migration.py`）。

這是全專案風險最高的一段程式碼：它會變更正式環境的資料，而且「已套用」的判斷完全
依賴 `_migrations` 資料表的記錄。記錄寫早了，失敗的 migration 會被當成跑過而永遠
不再重試；記錄寫晚了或漏寫，同一支就會重跑第二次。

不需要真的 PostgreSQL：`discover_migrations` 只碰檔案系統，`run_pending` 收的
`connection` 只用到 `execute()`（一次 SELECT、一次 INSERT），用假物件替換即可。因此
這裡是**單元測試**，不掛 `integration` 標記，本機沒有資料庫也會實際執行。
"""

from pathlib import Path
from typing import Any

import pytest

from shared.db.migration import (
    applied_versions,
    discover_migrations,
    run_pending,
)


class _FakeConnection:
    """只實作 `run_pending` 真正用到的 `execute()`，其餘一律不支援。

    以「SQL 字串裡有沒有 INSERT」分辨兩種呼叫，而不是比對完整語句 ——
    後者會讓這批測試在 `migration.py` 改一個空白字元時就整批紅燈。
    """

    def __init__(self) -> None:
        self.records: list[dict] = []

    async def execute(self, statement: Any, params: dict | None = None) -> Any:
        if "INSERT" in str(statement).upper():
            assert params is not None
            self.records.append(params)
            return None
        return [(record["version"],) for record in self.records]


def _write_migration(directory: Path, filename: str, body: str) -> None:
    (directory / filename).write_text(body, encoding="utf-8")


def _ok_migration(summary: str) -> str:
    return f'async def migrate(connection) -> str:\n    return "{summary}"\n'


def _failing_migration() -> str:
    return 'async def migrate(connection) -> str:\n    raise RuntimeError("boom")\n'


# --- discover_migrations -------------------------------------------------


def test_discover_migrations_sorts_by_filename(tmp_path: Path):
    """執行順序由檔名前綴決定，且不受建立順序影響。"""
    _write_migration(tmp_path, "0002_second.py", _ok_migration("second"))
    _write_migration(tmp_path, "0010_tenth.py", _ok_migration("tenth"))
    _write_migration(tmp_path, "0001_first.py", _ok_migration("first"))

    migrations = discover_migrations(tmp_path)

    # 零補齊的數字才會字典序 == 數值序：0010 必須排在 0002 之後。
    assert [m.version for m in migrations] == ["0001", "0002", "0010"]
    assert [m.name for m in migrations] == ["first", "second", "tenth"]


def test_discover_migrations_ignores_non_numeric_prefixed_files(tmp_path: Path):
    """只有數字開頭的檔案算 migration，輔助模組不會被誤當成一支。"""
    _write_migration(tmp_path, "0001_real.py", _ok_migration("real"))
    _write_migration(tmp_path, "_helpers.py", "VALUE = 1\n")
    _write_migration(tmp_path, "notes.py", "VALUE = 2\n")

    migrations = discover_migrations(tmp_path)

    assert [m.version for m in migrations] == ["0001"]


def test_discover_migrations_rejects_unpadded_version(tmp_path: Path):
    """沒有補齊到四位的檔名要立刻失敗，而不是等到第十支出現時才亂序。

    執行順序來自檔名的字串排序，所以 `10_x.py` 會排在 `9_x.py` **前面**。
    這種錯誤如果放行，症狀會是「某天新增第十支 migration 之後，順序悄悄變了」。
    """
    _write_migration(tmp_path, "1_unpadded.py", _ok_migration("unpadded"))

    with pytest.raises(RuntimeError, match="檔名不合規"):
        discover_migrations(tmp_path)


def test_discover_migrations_rejects_missing_description(tmp_path: Path):
    """只有版本號、沒有描述的檔名也不合規 —— `_migrations` 的 name 欄位會是空的。"""
    _write_migration(tmp_path, "0001.py", _ok_migration("nameless"))

    with pytest.raises(RuntimeError, match="檔名不合規"):
        discover_migrations(tmp_path)


def test_discover_migrations_rejects_duplicate_version(tmp_path: Path):
    """重複版本號要立刻失敗。

    同號 migration 會使其中一支永遠不會執行，因此必須在探索階段直接拒絕。
    """
    _write_migration(tmp_path, "0001_alice.py", _ok_migration("alice"))
    _write_migration(tmp_path, "0001_bob.py", _ok_migration("bob"))

    with pytest.raises(RuntimeError, match="版本重複"):
        discover_migrations(tmp_path)


def test_discover_migrations_rejects_module_without_migrate(tmp_path: Path):
    """缺 `migrate` 要在探索階段就炸掉，而不是輪到它才失敗。"""
    _write_migration(tmp_path, "0001_broken.py", "SOMETHING_ELSE = 1\n")

    with pytest.raises(RuntimeError, match="缺少"):
        discover_migrations(tmp_path)


def test_discover_migrations_on_empty_directory(tmp_path: Path):
    assert discover_migrations(tmp_path) == []


# --- repo 裡真正會被執行的那個目錄 -----------------------------------------
#
# 上面每一條都跑在 `tmp_path` 上，所以「檔名要補齊四位」與「版本號不可重複」這兩條規則
# 從來沒有對**真正會被 migrate 容器執行**的檔案問過話。commit 一支 `10_fix.py`
# 或兩支同號的 migration，CI 會全綠 —— 一路綠到部署當下 migrate 容器炸掉。
# 部署鏈本身仍然安全（api 等 migrate 成功結束），但發現時機從 CI 延到部署。

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "migrations"


def test_repo_migrations_are_wellformed():
    # 路徑解錯時 `discover_migrations` 會回空清單而不是失敗，那樣這條測試就變成恆真。
    assert MIGRATIONS_DIR.is_dir(), f"找不到 {MIGRATIONS_DIR}，這條測試會變成恆真"
    discover_migrations(MIGRATIONS_DIR)  # 不合規的檔名或重複版本號會直接 raise


def test_example_migration_is_not_discoverable():
    """`_example.py` 是撰寫範本，不可以被當成 migration 執行。

    它靠底線開頭天生不符合 `[0-9]*.py`，但那是「剛好」成立的 —— 這條把它釘住，
    順便證明上面那條真的掃到了東西，不是對著空目錄空轉。
    """
    assert (MIGRATIONS_DIR / "_example.py").is_file()
    assert [migration.name for migration in discover_migrations(MIGRATIONS_DIR)] == []


# --- applied_versions ----------------------------------------------------


@pytest.mark.asyncio
async def test_applied_versions_reads_recorded_versions():
    connection = _FakeConnection()
    connection.records.extend([{"version": "0001"}, {"version": "0002"}])

    assert await applied_versions(connection) == {"0001", "0002"}


# --- run_pending ---------------------------------------------------------


@pytest.mark.asyncio
async def test_run_pending_executes_all_and_records_them(tmp_path: Path):
    _write_migration(tmp_path, "0001_a.py", _ok_migration("a done"))
    _write_migration(tmp_path, "0002_b.py", _ok_migration("b done"))
    connection = _FakeConnection()

    executed = await run_pending(connection, tmp_path)

    assert executed == ["0001", "0002"]
    assert [record["version"] for record in connection.records] == ["0001", "0002"]
    # summary 是 migrate() 的回傳值，要一併留存下來供稽核。
    assert [record["summary"] for record in connection.records] == ["a done", "b done"]
    assert all("applied_at" in record for record in connection.records)


@pytest.mark.asyncio
async def test_run_pending_is_idempotent(tmp_path: Path):
    """重複執行不會重跑 —— 這是整個機制存在的理由。"""
    _write_migration(tmp_path, "0001_a.py", _ok_migration("a done"))
    connection = _FakeConnection()

    assert await run_pending(connection, tmp_path) == ["0001"]
    assert await run_pending(connection, tmp_path) == []
    assert len(connection.records) == 1


@pytest.mark.asyncio
async def test_run_pending_only_runs_new_migrations(tmp_path: Path):
    """已套用的略過，只跑新增的那一支。"""
    _write_migration(tmp_path, "0001_a.py", _ok_migration("a done"))
    _write_migration(tmp_path, "0002_b.py", _ok_migration("b done"))
    connection = _FakeConnection()
    connection.records.append({"version": "0001"})

    assert await run_pending(connection, tmp_path) == ["0002"]


@pytest.mark.asyncio
async def test_run_pending_does_not_record_failed_migration(tmp_path: Path):
    """失敗時不留記號，下次才可以重跑（`migration.py` 先執行後記錄的關鍵保證）。

    同時確認失敗會中止整批：0003 不該在 0002 失敗後還被執行。
    """
    _write_migration(tmp_path, "0001_ok.py", _ok_migration("ok"))
    _write_migration(tmp_path, "0002_boom.py", _failing_migration())
    _write_migration(tmp_path, "0003_later.py", _ok_migration("later"))
    connection = _FakeConnection()

    with pytest.raises(RuntimeError, match="boom"):
        await run_pending(connection, tmp_path)

    recorded = [record["version"] for record in connection.records]
    assert recorded == ["0001"], "只有成功的 0001 該被記錄"
    assert "0002" not in recorded, "失敗的 migration 不可留下已套用記號"
    assert "0003" not in recorded, "前一支失敗後不該繼續執行後續 migration"

    # 修好之後重跑，0002 與 0003 仍是待執行狀態。
    _write_migration(tmp_path, "0002_boom.py", _ok_migration("fixed"))
    assert await run_pending(connection, tmp_path) == ["0002", "0003"]


@pytest.mark.asyncio
async def test_run_pending_dry_run_reports_without_executing(tmp_path: Path):
    """dry-run 只列出待執行的版本，不執行也不寫入記錄。"""
    _write_migration(tmp_path, "0001_a.py", _ok_migration("a done"))
    # 這支一旦真的被執行就會拋例外，因此 dry-run 通過本身就證明它沒被呼叫。
    _write_migration(tmp_path, "0002_boom.py", _failing_migration())
    connection = _FakeConnection()

    assert await run_pending(connection, tmp_path, dry_run=True) == ["0001", "0002"]
    assert connection.records == []


@pytest.mark.asyncio
async def test_run_pending_dry_run_skips_already_applied(tmp_path: Path):
    _write_migration(tmp_path, "0001_a.py", _ok_migration("a done"))
    _write_migration(tmp_path, "0002_b.py", _ok_migration("b done"))
    connection = _FakeConnection()
    connection.records.append({"version": "0001"})

    assert await run_pending(connection, tmp_path, dry_run=True) == ["0002"]
