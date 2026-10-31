# 設計決策（ADR）

每份記錄一個「看起來可以換成更常見的做法、但刻意不換」的決定：當時的情境、選了什麼、代價是什麼。
想提議改掉其中一項之前先讀那一份，確認情境是不是真的變了。

功能**現在**怎麼運作寫在 [`features/`](../features/README.md) 與其他文件，這裡只寫**為什麼**。

## 寫法

- 照 [`_template.md`](_template.md) 的段落，檔名是 `NNNN-kebab-case.md`，編號接著最後一號往下。
- 寫好就不再改內容，只有狀態那一行與錯字可以改。
- 決定被推翻時另寫一份新的，三處一起改（測試會擋）：
  1. 新的那份在狀態下面加一行「取代：`[NNNN](NNNN-xxx.md)`」，取代多份時用「、」分隔。
  2. 舊的那份把狀態改成「被 `[NNNN](NNNN-xxx.md)` 取代（YYYY-MM-DD）」。
  3. 索引的狀態欄跟 ADR 的狀態一致：去掉日期，連結只留編號，例如「被 0009 取代」。

  之後也要更新描述現況的文件（`features/`、`operations.md` 等），把指向舊 ADR 的連結改到新的那份。
- 只推翻其中一部分時也整份取代：新的那份把舊決定裡仍然有效的部分寫進來，讀者只需要讀狀態是「採用」的那一份，
  不用把好幾份拼起來。需要部分推翻，通常代表舊的那份記了不只一個決定，之後寫 ADR 時一份只記一個決定。
- 模板佔用目前的編號，繼承的專案從下一號接著寫，不要重新編號。

## 索引

| 編號 | 決定 | 狀態 |
|---|---|---|
| [0001](0001-revoke-sessions-by-auth-version.md) | 用 `auth_version` 撤銷 session，不做 refresh token | 採用 |
| [0002](0002-no-web-signup.md) | 網頁不開註冊，超級管理者只能用指令建立 | 採用 |
| [0003](0003-centralized-permission-and-language.md) | `Permission` 與 `Language` 集中定義，不由模組動態組裝 | 採用 |
| [0004](0004-downtime-deploys.md) | 部署會短暫停機，api 維持單一行程 | 採用 |
| [0005](0005-in-process-rate-limit.md) | 限流計數放在行程記憶體 | 採用 |
| [0006](0006-postgres-job-queue.md) | 背景工作用 worker 容器與 PostgreSQL 佇列，不導入 Redis | 採用，尚未實作 |
| [0007](0007-seed-in-migrate-service.md) | 初始資料由 migrate 服務寫入，不用 Alembic 資料 migration | 採用 |
| [0008](0008-no-built-in-error-tracking.md) | 不內建錯誤追蹤與告警 | 採用 |
| [0009](0009-make-and-bash-commands.md) | 指令介面用 Makefile 加 bash 腳本 | 採用 |
| [0010](0010-full-repo-checkout-on-hosts.md) | 部署主機上 git clone 整份 repo | 採用 |
| [0011](0011-e2e-required-in-ci.md) | Playwright E2E 是 CI 與部署的必要檢查 | 採用 |
