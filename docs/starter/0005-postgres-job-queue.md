# 0005. 背景工作用 worker 容器與 PostgreSQL 佇列，不導入 Redis

設計規格見 [`extending/background-jobs.md`](../extending/background-jobs.md)。

## 決定

- 另開 worker 容器，用 api 的 image 換 command。佇列與排程都放 PostgreSQL（`FOR UPDATE SKIP LOCKED`）。
- **佇列自己寫**，不用現成的套件。
- 用 worker 心跳偵測掛掉的 worker，不用逐任務租約。
- 任務由模組在 `manifest.py` 宣告，worker 從 `ENABLED_MODULES` 收集。

模板還沒有 worker，第一個需要背景工作的功能照這份與設計規格實作，不要各做一套。

## 為什麼

主流做法是 Celery 或 arq 加 Redis。放在 PostgreSQL，任務就能跟業務資料寫在同一個交易裡，
不會出現「資料沒寫進去、信卻寄出去了」，也少一個服務。這是選 PostgreSQL 的主要理由。

PostgreSQL 佇列的現成套件（Procrastinate）只提供 psycopg 連線，表結構是套件自帶的 SQL 檔，
接不上專案的 SQLAlchemy + asyncpg 與 Alembic，也就拿不到同一個交易，所以自己寫。

## 代價

- 取任務、心跳、重試、排程的邊界情況要自己用測試守住；吞吐量較低，jobs 表要自己清理。
- 任務必須能重跑。

## 什麼時候重新檢討

需要管理介面、流程編排、超過 PostgreSQL 能承受的吞吐量，或自寫部分反覆出同類錯誤時。
先看當時的套件能否接上專案的連線與 migration。
