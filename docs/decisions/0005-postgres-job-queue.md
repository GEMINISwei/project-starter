# 0005. 背景工作用 worker 容器與 PostgreSQL 佇列，不導入 Redis

狀態：採用，尚未實作（2026-10-25）

## 背景

主流做法是 Celery 或 arq 加 Redis。模板目前沒有背景工作，但方向要先定，免得第一個需要的功能各做一套。
PostgreSQL 佇列的套件（Procrastinate）只提供 psycopg 連線，表結構是套件自帶的 SQL 檔，
接不上專案的 SQLAlchemy + asyncpg 與 Alembic。

## 決定

- 另開 worker 容器，用 api 的 image 換 command。佇列與排程都放 PostgreSQL（`FOR UPDATE SKIP LOCKED`）。
- **佇列自己寫**：任務才能跟業務資料寫在同一個交易裡，這是選 PostgreSQL 的主要理由。
- 用 worker 心跳偵測掛掉的 worker，不用逐任務租約。
- 任務由模組在 `manifest.py` 宣告，worker 從 `ENABLED_MODULES` 收集。

設計規格見 [`extending/background-jobs.md`](../extending/background-jobs.md)。

## 後果

- 少一個服務；不會出現「資料沒寫進去、信卻寄出去了」。
- 取任務、心跳、重試、排程的邊界情況要自己用測試守住；吞吐量較低，jobs 表要自己清理。
- 任務必須能重跑。
- 需要管理介面、流程編排、超過 PostgreSQL 能承受的吞吐量，或自寫部分反覆出同類錯誤時，
  重新檢討：先看當時的套件能否接上專案的連線與 migration。
