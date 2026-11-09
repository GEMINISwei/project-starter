# 模板的設計決定

這個專案由 project-starter 模板建立。這裡每一份記錄模板一個「看起來可以換成更常見的做法、但刻意不換」的決定：
決定是什麼、為什麼、代價，以及什麼時候該重新檢討。想提議改掉其中一項之前先讀那一份，確認情境是不是真的變了。

功能怎麼運作寫在 [`features/`](../features/README.md) 與其他文件，這裡只寫**為什麼**。

## 這一區不改

這一區跟著模板走，專案裡**不改、不新增**，才能直接跟模板比對，看出模板的決定有沒有變：

```bash
git diff --no-index docs/starter <模板的 checkout>/docs/starter
```

專案要推翻其中一份時，到 [`decisions/`](../decisions/README.md) 另寫一份，寫「取代：`starter/NNNN`」，
並列進那邊的〈推翻的模板決定〉。讀這一區之前，先看那張表有沒有列到你要讀的那一份。

在模板 repo 本身，決定變了就直接改寫那一份：這一區永遠只寫現況，不寫狀態、日期與演進過程（測試會擋）。

## 索引

| 編號 | 決定 |
|---|---|
| [0001](0001-revoke-sessions-by-auth-version.md) | 用 `auth_version` 撤銷 session，不做 refresh token |
| [0002](0002-no-web-signup.md) | 網頁不開註冊，超級管理者只能用指令建立 |
| [0003](0003-centralized-permission-and-language.md) | `Permission` 與 `Language` 集中定義，不由模組動態組裝 |
| [0004](0004-single-api-process.md) | api 維持單一行程：部署短暫停機、限流計數放記憶體 |
| [0005](0005-postgres-job-queue.md) | 背景工作用 worker 容器與 PostgreSQL 佇列，不導入 Redis |
| [0006](0006-seed-in-migrate-service.md) | 初始資料由 migrate 服務寫入，不用 Alembic 資料 migration |
| [0007](0007-no-built-in-error-tracking.md) | 不內建錯誤追蹤與告警 |
| [0008](0008-full-repo-checkout-on-hosts.md) | 部署主機上 git clone 整份 repo |
| [0009](0009-e2e-strategy.md) | E2E：CI 必跑正式環境 image，開發中用常駐的 dev 環境 |
| [0010](0010-no-environment-reviewer-for-deploys.md) | 部署不設 environment reviewer，由發布前的確認把關 |
| [0011](0011-agent-guardrails-by-judgment.md) | agent 防線以判斷為主，hook 只擋確認點 |
| [0012](0012-lock-mobile-zoom.md) | 手機上鎖住畫面縮放 |
| [0013](0013-cross-module-references-by-id.md) | 跨模組只以 ID 參照，但保留外鍵與共用交易 |
