# 0006. 背景工作用 worker 容器與 PostgreSQL 佇列，不導入 Redis

狀態：採用，尚未實作（2026-10-25）

## 背景

寄信、匯出報表、排程這類工作不該卡住請求。常見的做法是 Celery 或 arq 加上 Redis。
模板目前沒有背景工作，但方向要先定，免得第一個需要它的功能各自做一套。

用 PostgreSQL 當佇列的套件也是主流選項（Python 有 Procrastinate，Rails 8 預設的 Solid Queue 也是這一類）。
Procrastinate 的功能涵蓋我們要的大部分，但它只提供 psycopg 的連線，表結構是套件附帶、要照版本逐一執行的 SQL 檔。

## 決定

- 另開一個 worker 容器，跟 migrate 一樣用 api 的 image、換一個 command。
- 佇列放 PostgreSQL（`SELECT … FOR UPDATE SKIP LOCKED`），排程也放在同一個 worker。
- **佇列自己寫，不用套件**：專案的資料庫走 SQLAlchemy + asyncpg、結構走 Alembic，套件的連線與 migration
  接不上，任務就沒辦法跟業務資料寫在同一個交易裡，而這正是選 PostgreSQL 的主要理由。
- 用 **worker 心跳**偵測掛掉的 worker，不用逐任務的固定租約：任務跑多久都可以，worker 掛掉也很快被發現。
- 任務由模組在 `manifest.py` 宣告，worker 從 `ENABLED_MODULES` 收集。

完整的設計規格見 [`extending/background-jobs.md`](../extending/background-jobs.md)。

## 後果

- 少一個要維運與備份的服務，也少一個核心相依。
- 任務能跟業務資料寫在同一個交易裡，不會出現「資料沒寫進去、信卻寄出去了」。
- 取任務、心跳、重試、排程的邊界情況要自己用測試守住。
- 吞吐量比專門的佇列低；jobs 表的膨脹要自己清理。
- 任務必須能重跑：worker 可能做到一半被重啟。
- 需要管理介面、任務之間的流程編排、吞吐量超過 PostgreSQL 能承受的程度，或自己寫的部分反覆出現
  同類的錯誤時，重新檢討：先看當時的套件能不能跟專案的連線與 migration 接上。
