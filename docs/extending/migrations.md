# Migration

資料表**只由 migration 建立**（Alembic，revision 在 `apps/api/migrations/versions/`）。
漏寫 migration 時所有單元測試都是綠的，只有 `make check integration` 與 CI 會擋。

## 注意事項

autogenerate 固定會漏三件事，產出一定要讀：

| 它漏掉的 | 你要補的 |
|---|---|
| 往有資料的表加 NOT NULL 欄位，它只寫 `ADD COLUMN` | 給 `server_default`，或補一段回填 |
| 改名會被看成「drop 一個、add 一個」 | 改寫成 `op.alter_column(..., new_column_name=...)` |
| 不能在交易裡跑的 DDL（`CREATE INDEX CONCURRENTLY`） | 當成獨立的維運操作 |

- **兩版之間多了 migration 就不能回滾**，部署前的檢查會拒絕（見
  [`operations.md`](../operations.md#回滾與-migration)）。
- 改名與刪除仍建議拆成兩次發版（先加新的、兩邊並存，下一版才刪舊的）：部署時 migrate 先跑、
  程式後換，中間幾秒舊程式會跑在新結構上。
- 保持**一個 head**（`tests/test_migrations.py` 守），分岔了用 `alembic merge`。
- migration 裡**不要 import model**，用 `sa` 與 `op`；不要自己開交易或 `COMMIT`。
- 資料回填寫在 migration，不要寫進 `shared/platform.py` 的 lifespan。

## 發版之前可以整理

部署只認 release（[`operations.md`](../operations.md#自動部署)），所以還沒發布的 migration 不在任何主機上。
`make check migrate` 以**最近的 `v*` tag** 為界（prerelease 的 `v0.2.0-rc.1` 也算）：

| migration | 可以怎麼改 |
|---|---|
| 還沒有任何 tag（發 0.0.1 之前） | 全部都能改，結構變更直接併回初始 migration |
| 最近的 tag 之後才新增 | 合併、改寫、刪除都可以：同一個功能開發中途改了幾次結構，發版前併成一支 |
| 最近的 tag 之前就有 | **只往前**，不可修改或刪除，要改結構就新增一支 |

整理的步驟：把要合併的幾支改寫成一支（`down_revision` 接回 tag 時的 head），刪掉其餘的，
再 `make db reset` 重建本機資料庫，最後 `make check integration`（`alembic check` 確認與 model 一致）。

- **一起開發的人也要 `make db reset`**：他們的資料庫可能停在被刪掉的 revision，`migrate` 會找不到它而失敗。
- **prerelease 發出去之後就不能再整理**：它會部署到 staging，那裡的資料庫已經跑過這些 migration。
