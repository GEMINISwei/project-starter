---
name: feature-workflow
description: 開始任何要進 main 的改動時使用（新功能、修正、文件、設定）：開分支、驗收條件、先寫測試、Draft PR、實作、make check，到交給使用者審查。
---

# 從開分支到交給使用者審查

規則在 [`workflow.md`](../../../docs/workflow.md#開發流程) 與 [`testing.md`](../../../docs/testing.md)。

1. **開分支**：`gh pr list --author @me --state open` 有開著的 PR 就停下來回報；正式環境出問題才照 `hotfix`。
   沒有就從最新的 `main` 開 `<type>/<kebab-case>`。一個分支只做一件事，途中發現的別的問題記下來另開。
2. **驗收條件**：每條接一個測試名稱（前端與 E2E 用中文句子，後端 `test_<動作>_<條件>_<結果>`）。
   寫不出測試名稱的先問。**列給使用者確認才往下**，對話裡談定的方向也一樣。
3. **先寫測試**：放該 app 的 `tests/`，與原始碼同構；改到畫面流程時 E2E 也先寫。跑單項確認紅燈
   （`uv run pytest tests/ -k xxx`、`npm run test -- -t "名稱"`、`make e2e up` 後 `make e2e test <檔案>`）。
4. **commit 測試、push、開 Draft PR**：標題 Conventional Commits；描述照 [PR 模板](../../../.github/PULL_REQUEST_TEMPLATE.md)
   三段，驗收條件寫進「驗證」標「待實作」。commit 結尾加 `Co-authored-by`（寫到模型與版本）。
5. **實作**：測試變紅先改實作。要改測試先向使用者說明那個測試驗證的條件與沒過的原因，同意才改，
   並在「驗證」段寫出測試檔路徑與原本的斷言為什麼錯。
6. **收尾**：照 `AGENTS.md`〈改完之後〉補做（migration、`make gen-types`、`make check integration`、相關的 E2E），
   最後 `make check` 全綠。改到 nginx、compose 或只有正式環境才有的行為時加跑 `make check e2e`。
7. **交給使用者前自己審一次**（`git diff origin/main...HEAD`）：
   - 每條驗收條件有對應的測試，真的斷言到那個條件；diff 裡對不上任何一條的，是漏寫的條件或範圍外的改動
   - 沒有順手的格式、改名、無關修正，也沒有多出條件沒要求的抽象或設定
   - 新增的抑制註解同一行有理由；動到防線檔案、`AGENTS.md`、skills 的列進「檢查」段，說明會不會讓檢查變寬鬆
   - 行為或規則有變的，`AGENTS.md`、`docs/`、skills 一起改了
8. **更新 PR 描述**：「摘要」對上最新 diff，「驗證」每條寫結果（成功失敗都寫），「檢查」只列 diff 看不出、要人確認的事。
   push 後照 `watch-pr` 等 CI 並開始等合併，再回報使用者。Ready for review 與合併由使用者做。
