# 0006. 背景工作用 worker 容器與 PostgreSQL 佇列，不導入 Redis

狀態：採用，尚未實作（2026-10-25）

## 背景

寄信、匯出報表、排程這類工作不該卡住請求。常見的做法是 Celery 或 arq 加上 Redis。
模板目前沒有背景工作，但方向要先定，免得第一個需要它的功能各自做一套。

## 決定

- 另開一個 worker 容器，跟 migrate 一樣用 api 的 image、換一個 command。
- 佇列放 PostgreSQL（`SELECT … FOR UPDATE SKIP LOCKED`），排程也放在同一個 worker。
- 任務由模組在 `manifest.py` 宣告，worker 從 `ENABLED_MODULES` 收集。

## 後果

- 少一個要維運與備份的服務。
- 任務能跟業務資料寫在同一個交易裡，不會出現「資料沒寫進去、信卻寄出去了」。
- 吞吐量比專門的佇列低，任務量大到 PostgreSQL 撐不住時要重新檢討。
- 任務必須能重跑：worker 可能做到一半被重啟。

實作時要注意的事見 [`extending/background-jobs.md`](../extending/background-jobs.md)。
