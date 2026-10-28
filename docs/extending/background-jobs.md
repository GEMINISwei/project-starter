# 背景工作（尚未內建）

寄信、匯出報表、排程這類不該卡住請求的工作，模板還沒有提供，但方向已經定了
（[ADR 0006](../decisions/0006-postgres-job-queue.md)），加的時候照這個做：

- **另開一個 worker 容器**，跟 `migrate` 一樣用 api 的 image、換一個 command，程式與 model 共用。
- **佇列放 PostgreSQL**（`SELECT … FOR UPDATE SKIP LOCKED`），**不導入 Redis**：少一個要維運與備份的
  服務，而且任務能跟業務資料寫在**同一個交易**裡，不會出現「資料沒寫進去、信卻寄出去了」。
  排程（每天固定時間跑）也放在同一個 worker，不另開容器。
- **每個任務要自己開 session**：HTTP 請求的 session 由 middleware 開，worker 沒有這一層，
  由 worker 的框架統一包 `session_scope()`，不要讓每個任務自己記（見 `shared/db/session.py`）。
- **worker 不跑 seed**：seed 屬於 migrate 服務，只在部署時跑一次（見〈[初始資料](seed.md)〉）。
- **任務要能重跑**：worker 可能在做到一半時被重啟（部署、OOM），重跑一次不能出錯或重複寄信。
- **任務由模組在 `manifest.py` 宣告**，worker 從 `ENABLED_MODULES` 收集（比照 router），
  模組整包刪掉時任務才會跟著消失。
