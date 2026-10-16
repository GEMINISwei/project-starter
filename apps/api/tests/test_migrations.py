"""Alembic 接線的靜態保證。

`alembic upgrade` 本身是上游的程式碼, 不需要我們測。這裡守的是**接線錯掉之後不會有
症狀**的那幾件事 —— 都不需要資料庫, 所以本機一定會實際執行:

1. **剛好一個 head。** 兩個人各自從同一個 revision 分支出去時, Alembic 會在
   `upgrade head` 當下報 "Multiple head revisions", 而那是**部署時**才發生 ——
   migrate 容器失敗、api 等不到它、整個部署卡住。這條讓它在 PR 上就紅。
   「剛好一個」也同時擋掉 `versions/` 是空的 (零個 head): 應用程式沒有任何自動建表的
   路徑, 空目錄等於部署出去是一個沒有任何資料表的資料庫。
2. **`env.py` 的 metadata 真的裝滿了表。** autogenerate 比對的是
   `target_metadata`; 如果 `app.registry` 那個 import 被誰「清掉未使用的 import」
   拿掉了, metadata 會是空的, 而 autogenerate 會安靜地產出一支
   **把所有表都 DROP 掉**的 migration。
3. **約束有命名慣例。** 少了它, autogenerate 產不出能執行的「刪除約束」。

`alembic check` (model 與 migration 有沒有漂移) 需要真的資料庫, 在
`make check integration` 的第二段 (CI 也跑), 不在這裡。
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

API_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = API_ROOT / "alembic.ini"


def _script_directory() -> ScriptDirectory:
    assert ALEMBIC_INI.is_file(), f"找不到 {ALEMBIC_INI}，底下每條測試都會變成恆真"
    return ScriptDirectory.from_config(Config(str(ALEMBIC_INI)))


def test_migrations_have_exactly_one_head():
    heads = _script_directory().get_heads()

    assert len(heads) == 1, (
        f"有 {len(heads)} 個 head：{heads}。"
        " 兩支 migration 指向同一個 down_revision 時會這樣 ——"
        " 用 `alembic merge` 併成一支，或把其中一支的 down_revision 接到另一支後面。"
    )


def test_target_metadata_covers_every_registered_table():
    """`env.py` 拿到的 metadata 要涵蓋註冊表上的每一張表。

    這裡重現 `env.py` 的組法 (import `app.registry`, 再讀 `BaseTable.metadata`),
    而不是 import `env.py` 本身 —— 那支在 import 當下就會去連資料庫並跑 migration。
    """
    import app.registry  # noqa: F401 —— import 的副作用才是重點
    from app.registry import TABLE_MODELS
    from shared.db.table import BaseTable

    registered = {model.__tablename__ for model in TABLE_MODELS}

    assert registered, "註冊表上一張表都沒有，這條測試會變成恆真"
    assert registered <= set(BaseTable.metadata.tables)


def test_metadata_has_naming_convention():
    """約束命名慣例是 autogenerate 能正確產出「刪除某個約束」的前提。

    少了它, `UniqueConstraint` 在 metadata 裡的 name 是 None, 而 autogenerate 會產出
    `op.drop_constraint(None, ...)` —— 一句跑不起來的 SQL, 且要到那次改動時才發現。
    """
    from shared.db.table import BaseTable

    convention = BaseTable.metadata.naming_convention

    assert {"pk", "uq", "fk", "ix", "ck"} <= set(convention)
