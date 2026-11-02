# 背景工作（尚未內建）

寄信、匯出報表、處理上傳的圖片、呼叫外部服務、每天固定時間跑的工作，都不該卡在請求裡。模板還沒有
提供 worker，但方向已經定了（[ADR 0006](../decisions/0006-postgres-job-queue.md)）。這份是**設計規格**：
繼承的專案照這份實作，各專案的 worker 才會有一致的行為，每一條「規則」都要有對應的測試。

這裡的 worker 是**另一個執行背景工作的容器**，跟 uvicorn 的 workers（多個 api 行程）無關。
後者仍然不能加，理由見 [ADR 0004](../decisions/0004-downtime-deploys.md) 與 [ADR 0005](../decisions/0005-in-process-rate-limit.md)。

## 什麼時候該交給 worker

符合任一條就不要在請求裡做：

- **慢**：使用者不該等它做完才拿到回應。
- **吃 CPU 或記憶體**：api 是單一行程，做這種事會拖慢同時間的所有請求。
- **要重試**：外部服務會失敗，失敗了要稍後再試，而不是讓使用者重送。
- **要定時**：每天、每小時固定跑。
- **會瞬間湧入**：一次進來大量事件，要排隊慢慢消化，而不是同時處理。

結果要在同一個回應裡給使用者的，留在請求裡做。

## 架構

```
請求 ──► api ──(同一個交易)──► 業務資料 + jobs 表
                                   │ NOTIFY
                                   ▼
                                worker（同一個 image，不同的 command）
                                   ├─► 執行任務、寫回結果
                                   └─► 檔案存到 /app/uploads/<模組>/
```

- **另開一個 worker 容器**，跟 `migrate` 一樣用 api 的 image、換一個 command，程式與 model 共用。
- **佇列是 PostgreSQL 裡的一張表，自己寫**，不導入 Redis，也不用 Celery、Procrastinate 這類套件。
  理由見 ADR 0006：任務要能跟業務資料寫在同一個交易裡，而那些套件用的連線與 migration 方式跟
  專案（SQLAlchemy + asyncpg、Alembic）接不起來。
- **任務由模組在 `manifest.py` 宣告**，worker 從 `ENABLED_MODULES` 收集（比照 router），
  模組整包刪掉時任務才會跟著消失。
- **每個任務要自己開 session**：HTTP 請求的 session 由 middleware 開，worker 沒有這一層，
  由 worker 的框架統一包 `session_scope()`，不要讓每個任務自己記（見 `shared/db/session.py`）。
- **worker 不跑 seed**：seed 屬於 migrate 服務，只在部署時跑一次（見〈[初始資料](seed.md)〉）。

## 任務的狀態

```
pending ──取走──► running ──成功──────────────────────► succeeded
   ▲                 ├─可重試的失敗、還沒到上限 ──► pending（run_at 往後延）
   │                 └─不可重試的失敗、或到了上限 ─► dead
   └──── worker 心跳停了（掛掉、被 OOM kill）────┘
```

jobs 表至少要有：

| 欄位 | 用途 |
|---|---|
| `queue`、`kind`、`payload` | 哪條佇列、哪種任務、任務的參數 |
| `status`、`attempts`、`max_attempts` | 狀態與重試次數 |
| `run_at` | 最早什麼時候可以執行；延遲任務、重試的退避都靠它 |
| `worker_id` | 現在由哪個 worker 執行，用來救回掛掉的 worker 手上的任務 |
| `idempotency_key` | 唯一鍵，同一件事只會建立一筆任務 |
| `last_error`、`created_at`、`finished_at` | 除錯與清理 |

## 設計規則

### 寫入：跟業務資料在同一個交易

- 業務資料與任務一起 commit。不會出現「資料寫進去了、任務沒建立」，或反過來的情況。
- 外部事件用它自己的 ID 當 `idempotency_key`，外部服務重送同一個事件時只會建立一筆任務。
- 收外部事件的端點只做驗證與寫入，就立刻回應，不在請求裡處理。

### 取任務：`FOR UPDATE SKIP LOCKED`

- 取 `status = pending` 且 `run_at <= now()` 的任務，一次取的數量等於這條佇列剩下的並行數。
- `SKIP LOCKED` 讓多個 worker（或同一個 worker 的多個執行單位）不會搶到同一筆。

### 偵測掛掉的 worker：心跳

- 每個 worker 在資料庫有一列，固定每隔幾秒更新一次時間。超過門檻沒更新，就把它名下所有 `running`
  的任務改回 `pending`。
- **不用逐任務的固定租約**：租約設短，長任務還沒做完就被當成卡住，同一個任務會被做兩次；設長，
  worker 掛掉後要等很久才會重跑。心跳把「worker 還活著嗎」跟「任務要跑多久」分開，任務跑多久都可以。
- 門檻要比心跳間隔長好幾倍（例如每 10 秒一次、30 秒沒更新才算掛掉），避免一次短暫延遲就誤判。
- 同一個心跳迴圈也更新容器裡的心跳檔，給 healthcheck 用（見〈[加 worker 時要一起改的地方](#加-worker-時要一起改的地方)〉）。

### 執行：能重跑、有時間上限

- **任務一定會被執行至少一次，可能不只一次**：做到一半被重啟（部署、OOM、主機重開）後會重跑，
  重跑不能出錯，也不能重複產生副作用（重複寄信、重複扣款）。
- **每種任務都有執行時間上限**，超過就當成失敗。
- **吃 CPU 的任務在子行程裡跑**：Python 沒辦法強制中斷一條正在跑同步程式的執行緒，`asyncio` 的逾時
  只對 async 程式碼有效。放在子行程裡，逾時就直接結束子行程；記憶體爆掉也只死子行程。
  主迴圈因此一直有空，心跳不會被卡住。

### 重試與死信

- 失敗時 `attempts + 1`，`run_at = 現在 + 基數 × 2^attempts + 隨機值`。隨機值避免大量任務在同一時間一起重試。
- **區分錯誤種類**：暫時性的（外部服務逾時、連線中斷）才重試；永久性的（資料格式錯誤、找不到資源）
  直接標成 `dead`，重試也不會成功。
- 到了 `max_attempts` 就標成 `dead`，**不刪除**，保留 `last_error`，修好原因後可以手動重新排入。
  每次都讓 worker 當掉的「毒任務」也會在這裡停下，不會無限循環。

### 分佇列

- 每條佇列有自己的並行數，例如吃 CPU 的佇列並行 1、一般的佇列並行 4。
- 只有一條佇列時，一批慢任務會擋住後面所有的快任務（寄信要等上百張圖片處理完）。

### 排程

- 延遲任務：`run_at` 設在未來。
- 固定時間的排程：用「（任務種類、預定時間）」當 `idempotency_key` 寫入任務。worker 重啟、多跑一次都不會
  重複；停機期間錯過的，每種排程自己決定要補跑還是跳過。
- 排程與任務放在同一個 worker，不另開容器。

### 叫醒：`LISTEN/NOTIFY` 加上保底輪詢

- 寫入任務時發 `NOTIFY`，worker 立刻醒來，不用每秒輪詢。
- 另外每 30～60 秒輪詢一次當保底：到期的延遲任務不會發通知，worker 重連期間的通知也會漏掉。

### 關機：處理 SIGTERM

- 收到 SIGTERM 後停止取新任務，等手上的做完再結束。
- compose 的 `stop_grace_period` 預設 10 秒，任務比這個長就要調長；來不及做完的，交給心跳機制重跑。

### 清理：處理表的膨脹

- jobs 表會頻繁地新增、更新、刪除，留下大量 dead tuples。
- `succeeded` 的任務保留一段時間後刪除，`dead` 的保留更久或等人處理；清理本身也是一個排程任務。
- 把 jobs 表的 autovacuum 調得比預設積極（例如調低 `autovacuum_vacuum_scale_factor`），寫在建表的 migration 裡。

## 資源：不拖累同一台主機的其他服務

worker 是背景工作，晚幾秒完成沒人察覺，所以可以限速；api、web、postgres 要即時回應，**不設 CPU 上限**。

| 層次 | 做法 |
|---|---|
| 程式 | 每條佇列的並行數固定；處理前先限制輸入大小（檔案大小、圖片像素數）；OpenCV、numpy 這類函式庫預設會用到所有核心，用 `OMP_NUM_THREADS` 等設定壓住 |
| 容器（prod overlay） | `cpus:` 設硬性上限，數字配合並行數；`cpu_shares` 設得比其他容器低，主機忙時先讓；記憶體上限也要設（任務能重跑，被 OOM kill 只會重試） |
| 佇列 | 瞬間湧入的量變成排隊的任務，而不是 CPU 的尖峰 |

**限速影響的是速度，不是可靠性**：任務不會因為被限速而遺失。前提是處理速度要大於**平均**進來的速度，
所以要看下面的指標。

## 要看的指標

- **最舊一筆 `pending` 任務等了多久**：持續變大就代表處理不完。這是最重要的一個。
- 各狀態的任務數，特別是 `dead` 的數量。
- log 每筆都帶任務 ID、種類與嘗試次數。

## 加 worker 時要一起改的地方

| 位置 | 要改什麼 |
|---|---|
| `infra/docker/docker-compose.yml` | 新增 worker 服務：共用 `x-api-image` 錨點、換 command、`depends_on` postgres 健康與 migrate 成功結束、掛 `uploads` volume、`restart: always`、`stop_grace_period` |
| worker 的 healthcheck | 檢查心跳檔夠不夠新（例如 `find /tmp/heartbeat -mmin -1`），**不要起 Python 載入整個 app**：每次要花上秒的 CPU，而且程式卡住時載入照樣成功。間隔同其他服務：啟動期間每秒、之後每 30 秒（見〈[可觀測性只到 stdout](../operations.md#可觀測性只到-stdout)〉，`tests/test_compose_healthchecks.py` 擋） |
| `infra/docker/docker-compose.prod.yml` | log 上限（`*prod-runtime`）、記憶體上限、`cpus:`、較低的 `cpu_shares` |
| `scripts/backup.sh` | **備份期間也要停 worker**：現在的前提是「停掉 nginx 就沒有寫入」，worker 會繼續寫資料庫與上傳檔案，備份出來的兩邊就對不上 |
| [`operations.md`](../operations.md) | 正式環境的記憶體上限清單加上 worker；主機記憶體要容得下所有服務的上限加總 |
