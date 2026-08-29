"""Migration 的撰寫範本 —— **這個檔案不會被執行**。

`discover_migrations()` 只撿 `[0-9]*.py`（數字開頭），底線開頭的檔案天生不會被收錄，
所以這份範本可以安全地留在目錄裡當參考。要寫真的 migration 時，複製一份改名：

    cp _example.py 0001_add_item_category.py

然後執行：

    make migrate                    # 套用所有未執行的

正常部署不需要手動跑：compose 有一個一次性的 migrate service，backend 會等它成功結束
才啟動（見 infra/docker/docker-compose.yml）。`make migrate` 是給維運與驗證用的。


## 什麼時候需要寫 migration

**新增一整張資料表不用寫。** `make migrate` 會先跑 `create_missing_tables()`，
依 model 定義補上還不存在的表與索引（見 shared/db/migration.py）。

**改既有的表一定要寫。** 新增／刪除欄位、改型別、改索引、改約束、回填資料 ——
`create_all` 只新增、不修改，所以這些變更沒有 migration 就完全不會發生，
而服務會照常啟動，直到第一次讀寫那個欄位才炸。


## 規範

1. **檔名** `NNNN_描述.py`，編號**零補齊**四位。執行順序由檔名字串排序決定，
   所以 `0010` 必須寫成 `0010` 而不是 `10`，否則會排在 `0002` 前面。
   這條規則與「版本號不可重複」都由 `discover_migrations()` 強制檢查，不符合會直接失敗。
2. **必須匯出 `async def migrate(connection) -> str`。** `connection` 是 SQLAlchemy 的
   `AsyncConnection`，用 `text()` 直接下 SQL（不要 import model —— migration 的對象
   常常是「已經改掉或即將刪掉」的舊結構，綁上目前的 model 只會讓它跑不起來）。
3. **回傳值是稽核紀錄。** 它會連同版本、名稱、時間寫進 `_migrations` 資料表，
   所以請回傳有意義的摘要（改了幾筆、略過的原因），不要回傳空字串。
4. **必須可以重複執行。** 雖然 `_migrations` 擋住了重跑，但前一次可能跑到一半才失敗
   （失敗時**不會**留下已套用的記號，正是為了讓你能修好再跑一次）。所以 DDL 一律帶
   `IF EXISTS` / `IF NOT EXISTS`，資料更新一律先檢查當前狀態。
5. **不要假設資料存在。** 全新專案跑 migration 時表可能剛建好而且是空的，
   要正常略過而不是拋錯。
6. **不用自己開交易。** 整批 migration 由 `scripts/db.py migrate` 包在一個交易裡，
   任何一支失敗就整批回滾。**也因此不要在裡面 `COMMIT`** —— 那會把交易邊界切開，
   後面的 migration 失敗時前面的就回不去了。
7. **沒有 rollback。** 結構變更多半無法無損還原，假裝可以反而危險。
   需要回退請從備份還原（`make backup` / `make restore`）。


## 三種常見寫法

底下是實際會用到的範例，複製後把不需要的刪掉。
"""

from sqlalchemy import text


async def migrate(connection) -> str:
    # ── 寫法 1：新增欄位並補上預設值（最常見） ──────────────────────────
    #
    # `ADD COLUMN IF NOT EXISTS` 讓這一步可以重跑。`DEFAULT` 會讓既有的列一併填上，
    # 所以不需要另一句 UPDATE —— 但**新欄位若要 NOT NULL，DEFAULT 必須同時給**，
    # 否則既有的列會是 NULL 而違反約束，整句直接失敗。
    await connection.execute(
        text(
            "ALTER TABLE items "
            "ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'uncategorized'"
        )
    )

    # ── 寫法 2：建立索引 ────────────────────────────────────────────────
    #
    # `IF NOT EXISTS` 讓它冪等。**不要用 `CONCURRENTLY`** —— 那個不能在交易裡跑，
    # 而這整批 migration 是同一個交易（見上面的規範 6）。資料量大到不能鎖表時，
    # 請把那次索引建立當成一次獨立的維運操作，不要塞進 migration。
    await connection.execute(
        text("CREATE INDEX IF NOT EXISTS ix_items_category ON items (category)")
    )

    # ── 寫法 3：改名／搬移資料表 ────────────────────────────────────────
    #
    # 先確認來源存在，全新專案沒有舊表時要正常略過。
    # `to_regclass()` 回傳 NULL 代表那個名字目前不指向任何資料表。
    exists = await connection.scalar(text("SELECT to_regclass('old_items')"))
    if exists is None:
        renamed = "沒有 old_items，略過改名（全新專案的正常情況）"
    else:
        await connection.execute(text("ALTER TABLE old_items RENAME TO items"))
        renamed = "old_items 已改名為 items"

    # 回傳值會寫進 `_migrations`，寫清楚做了什麼。
    return f"items 補上 category 欄位；建立 ix_items_category；{renamed}"
