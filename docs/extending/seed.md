# 初始資料（Seed）

定義在 model class 上，由 **migrate 服務**在 `alembic upgrade head` 之後以 `BaseTable.ensure_seed()`
寫入（`scripts/db.py migrate`）。`make start`、`make db migrate`、`make db reset` 都會經過它；
api 開機時**不寫任何資料**（[ADR 0007](../decisions/0007-seed-in-migrate-service.md)）。所以 seed 失敗跟 migration 失敗一樣，會被 `make start`「migrate 失敗就不切換服務」
擋下（見 [`operations.md`](../operations.md#生產部署)）：


| class variable | 說明 |
|---|---|
| `seed_data` | 初始資料的 `list[dict]` |
| `seed_match_key` | **有設**：每次 migrate 都依此欄位 upsert（欄位必須有唯一約束，多個行程同時跑也安全）；**沒設**：只在表為空時寫入（同時跑會重複寫入，只能在一個行程裡跑） |
| `prepare_seed_item()` | 選用，寫入前轉換資料（例如雜湊密碼） |

`RoleTable` 設了 `seed_match_key = "code"`，所以系統角色的權限與名稱在每次部署時都會同步回模板的定義。
改了 `seed_data` 之後，開發機跑 `make db migrate` 就會套用。
