# 設計決策（ADR）

每份記錄一個「看起來可以換成更常見的做法、但刻意不換」的決定：當時的情境、選了什麼、代價是什麼。
想提議改掉其中一項之前先讀那一份，確認情境是不是真的變了。

功能**現在**怎麼運作寫在 [`features/`](../features/README.md) 與其他文件，這裡只寫**為什麼**。

## 寫法

- 照 [`_template.md`](_template.md)，檔名 `NNNN-kebab-case.md`，編號接著最後一號。一份只記一個決定。
- 寫好不改內容，只改狀態與錯字。決定被推翻時另寫一份，三處一起改（測試會擋）：
  新的寫「取代：`[NNNN](NNNN-xxx.md)`」；舊的狀態改成「被 `[NNNN](NNNN-xxx.md)` 取代（YYYY-MM-DD）」；
  索引狀態欄同步（去掉日期）。部分推翻也整份取代，並更新指向舊 ADR 的文件連結。
- 例外是討論後**維持原決定**的紀錄（例如 `project-review` skill 的反對結論），讓下次審視知道討論過什麼。
  以最近的 `v*` tag 為界，和 [migration](../extending/migrations.md#發版之前可以整理) 一樣：
  - **還沒有任何 tag**：直接改寫那份的「背景」或「後果」，把結論併進去，不留討論紀錄。
  - **有 tag 之後**：在最後的 `## 後續討論` 往下追加一筆，前面的段落不動。格式：

  ```markdown
  ## 後續討論

  ### YYYY-MM-DD <在哪裡提出，例如專案審視>
  - 提出：<項目與一句摘要>
  - 結論：維持原決定
  - 理由：<兩三句>
  ```
- 模板佔用目前的編號，繼承的專案從下一號接著寫。

## 索引

| 編號 | 決定 | 狀態 |
|---|---|---|
| [0001](0001-revoke-sessions-by-auth-version.md) | 用 `auth_version` 撤銷 session，不做 refresh token | 採用 |
| [0002](0002-no-web-signup.md) | 網頁不開註冊，超級管理者只能用指令建立 | 採用 |
| [0003](0003-centralized-permission-and-language.md) | `Permission` 與 `Language` 集中定義，不由模組動態組裝 | 採用 |
| [0004](0004-single-api-process.md) | api 維持單一行程：部署短暫停機、限流計數放記憶體 | 採用 |
| [0005](0005-postgres-job-queue.md) | 背景工作用 worker 容器與 PostgreSQL 佇列，不導入 Redis | 採用，尚未實作 |
| [0006](0006-seed-in-migrate-service.md) | 初始資料由 migrate 服務寫入，不用 Alembic 資料 migration | 採用 |
| [0007](0007-no-built-in-error-tracking.md) | 不內建錯誤追蹤與告警 | 採用 |
| [0008](0008-full-repo-checkout-on-hosts.md) | 部署主機上 git clone 整份 repo | 採用 |
| [0009](0009-e2e-strategy.md) | E2E：CI 必跑正式環境 image，開發中用常駐的 dev 環境 | 採用 |
| [0010](0010-no-environment-reviewer-for-deploys.md) | 部署不設 environment reviewer，由發布前的確認把關 | 採用 |
| [0011](0011-agent-guardrails-by-judgment.md) | agent 防線以判斷為主，hook 只擋確認點 | 採用 |
| [0012](0012-lock-mobile-zoom.md) | 手機上鎖住畫面縮放，像原生 App | 採用 |
| [0013](0013-cross-module-references-by-id.md) | 跨模組只以 ID 參照，但保留外鍵與共用交易 | 採用 |
