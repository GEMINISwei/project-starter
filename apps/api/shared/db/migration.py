"""版本化的資料庫 migration 執行器。

資料結構的一次性變更使用以下最小可用的版本化機制：

- migration 是 `scripts/migrations/NNNN_描述.py`，每支匯出
  `async def migrate(connection) -> str`
- 已套用的版本記錄在 `_migrations` 資料表，跑過的不會再跑
- 依檔名排序依序執行，任何一支失敗就中止（不會標記為已完成）

**建立新資料表不需要寫 migration**：`create_missing_tables()` 會依 model 定義補上
還不存在的表與索引（`CREATE TABLE IF NOT EXISTS` 的語義），這是 Beanie 時代
`init_beanie` 自動建 collection 與索引那個行為的替代品。但它**只新增、不修改** ——
替既有資料表增刪欄位、改型別、改索引選項一律要寫一支 migration。這個分界很重要：
改了 model 的欄位卻沒寫 migration，服務會照常啟動，直到第一次讀寫那個欄位才炸。

刻意**不做**自動 rollback：結構變更多半無法無損還原，假裝可以反而危險。
需要回退時請從備份還原（`make backup` / `make restore`）。

**刻意不引入 Alembic。** 它能自動產生 diff，但代價是一套 revision 圖、`env.py` 與
autogenerate 的審閱流程；這個模板要的是「一支檔案、一個版本號、看得懂就會寫」。
真的長到需要分支式的 revision 圖時再換，那時這裡的 `_migrations` 資料表可以直接
當成 Alembic 的起點版本。
"""

import importlib.util
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, text

MIGRATION_TABLE = "_migrations"

# 這三句 SQL 拼進了表名。S608（SQL injection）在這裡是誤報：拼進去的是本模組的常數，
# 不是外部輸入 —— 而表名本來就不能用綁定參數。所有**值**一律走綁定參數。
_SELECT_VERSIONS = f'SELECT version FROM "{MIGRATION_TABLE}"'  # noqa: S608
_INSERT_VERSION = (
    f'INSERT INTO "{MIGRATION_TABLE}" (version, name, applied_at, summary)'  # noqa: S608
    " VALUES (:version, :name, :applied_at, :summary)"
)
_CREATE_TABLE = f'''
    CREATE TABLE IF NOT EXISTS "{MIGRATION_TABLE}" (
        version    TEXT PRIMARY KEY,
        name       TEXT NOT NULL,
        applied_at TIMESTAMP NOT NULL,
        summary    TEXT NOT NULL
    )
'''

# 檔名規則：四位數字 + 底線 + 描述。
#
# 「四位」不是美觀問題，是正確性問題 —— 執行順序來自檔名的**字串**排序，
# 所以 `10_xxx.py` 會排在 `9_xxx.py` 前面。
MIGRATION_FILENAME_PATTERN = re.compile(r"^\d{4}_.+\.py$")


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    run: Callable[[Any], Awaitable[str]]


def discover_migrations(directory: Path) -> list[Migration]:
    """載入目錄下所有 `NNNN_*.py`，依檔名排序。

    檔名前綴決定執行順序，所以請用零補齊的四位數字（0001、0002…）。
    不符合規則的檔名、或重複的版本號，都會在這裡立刻失敗——**不是**被略過。
    """
    migrations: list[Migration] = []
    seen: dict[str, str] = {}

    # glob 的 `[0-9]` 只保證第一個字元是數字，所以輔助模組（`_helpers.py`、`notes.py`）
    # 本來就不會被撿走。但它擋不住 `1_foo.py` 這種沒有補齊的檔名，那個要靠下面的
    # MIGRATION_FILENAME_PATTERN。
    for path in sorted(directory.glob("[0-9]*.py")):
        if not MIGRATION_FILENAME_PATTERN.match(path.name):
            raise RuntimeError(
                f"migration 檔名不合規：{path.name}"
                "（必須是四位數字 + 底線 + 描述，例如 0001_add_field.py）"
            )

        version, _, name = path.stem.partition("_")

        # 重複版本號會使第二支 migration 永遠不會執行，因此必須立即失敗。
        if version in seen:
            raise RuntimeError(
                f"migration 版本重複：{version} 同時出現在 {seen[version]} 與 {path.name}"
            )
        seen[version] = path.name

        spec = importlib.util.spec_from_file_location(f"migrations.{path.stem}", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"無法載入 migration：{path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        run = getattr(module, "migrate", None)
        if run is None:
            raise RuntimeError(f"{path.name} 缺少 `async def migrate(connection) -> str`")

        migrations.append(Migration(version=version, name=name or path.stem, run=run))

    return migrations


async def create_missing_tables(connection: Any, metadata: MetaData) -> None:
    """依 model 定義補上還不存在的資料表與索引（見模組 docstring 的分界說明）。

    `checkfirst=True` 是 `create_all` 的預設值，這裡寫出來是因為它正是這個函式安全的
    理由：既有的表一律不碰，所以可以在每次部署都跑。
    """
    await connection.run_sync(metadata.create_all, checkfirst=True)


async def ensure_migration_table(connection: Any) -> None:
    """建立 `_migrations` 資料表。

    `version` 是主鍵，防的是**重複記錄**，不是併發鎖 —— 兩個同時啟動的 runner 仍會
    各自執行 migration 本體，只是輸的那個會在寫記錄時失敗（而且是在資料已經被改完
    之後）。真正的互斥要靠「同時只跑一個 migrate」這個部署層的保證，compose 的一次性
    migrate service 就是在提供它。不要依賴主鍵來做併發保護。
    """
    await connection.execute(text(_CREATE_TABLE))


async def applied_versions(connection: Any) -> set[str]:
    result = await connection.execute(text(_SELECT_VERSIONS))
    return {row[0] for row in result}


async def run_pending(connection: Any, directory: Path, *, dry_run: bool = False) -> list[str]:
    """執行所有尚未套用的 migration，回傳這次實際跑過的版本。"""
    from shared.time import utc_now

    done = await applied_versions(connection)
    executed: list[str] = []

    for migration in discover_migrations(directory):
        if migration.version in done:
            continue

        if dry_run:
            print(f"[dry-run] 待執行 {migration.version} {migration.name}")
            executed.append(migration.version)
            continue

        print(f"執行 {migration.version} {migration.name} …")
        summary = await migration.run(connection)
        # 先跑完、確定沒有丟出例外才記錄。失敗時不留下記號，下次可以重跑。
        await connection.execute(
            text(_INSERT_VERSION),
            {
                "version": migration.version,
                "name": migration.name,
                "applied_at": utc_now(),
                "summary": summary,
            },
        )
        print(f"  完成：{summary}")
        executed.append(migration.version)

    return executed
