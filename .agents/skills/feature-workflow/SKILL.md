---
name: feature-workflow
description: 開始任何要進 main 的改動時使用（新功能、修正、文件、設定）：開分支、在 Draft PR 寫驗收條件、先寫測試、實作、make check，到 Ready for review 的步驟。
---

# 從開分支到 Ready for review

規則的完整說明在 [`workflow.md`](../../../docs/workflow.md#開發流程) 與
[`testing.md`](../../../docs/testing.md)，這裡只列步驟與容易漏的地方。

1. **開分支**：從最新的 `main` 開 `<type>/<kebab-case>`。一個分支只做一件事，途中發現別的問題就記下來另開。
2. **先寫驗收條件**：每條接一個測試名稱（前端與 E2E 用中文句子，後端用 `test_<動作>_<條件>_<結果>`）。
   寫不出測試名稱的那條，先停下來問使用者，不要自己猜。
3. **先寫測試**：單元測試放該 app 的 `tests/`，與原始碼同構；會改到畫面流程時 E2E 也先寫。
   跑單項確認是紅燈（`uv run pytest tests/ -k xxx`、`npm run test -- -t "名稱"`）。
4. **commit 測試、push、開 Draft PR**：PR 標題用 Conventional Commits；描述照
   [PR 模板](../../../.github/PULL_REQUEST_TEMPLATE.md) 的三段，驗收條件寫進「驗證」並標「待實作」。
   commit 最後加 `Co-authored-by`（寫到模型與版本）。
5. **實作**：測試檔此時鎖定。測試變紅先改實作；真的認為測試要改，先向使用者說明那個測試驗證的條件、
   沒過的原因，得到同意才改，並在 PR 描述寫明原本的斷言為什麼錯。
6. **收尾**：照 `AGENTS.md`〈改完之後〉的表補做（migration、`make gen-types`、`make check integration`、
   `make check e2e`），最後 `make check` 全綠。
7. **更新 PR 描述**：「摘要」對上最新的 diff，「驗證」每條寫上結果（成功失敗都寫），
   「檢查」只列 diff 看不出來、要有人去確認的事。push 之後改用 `watch-pr` 這個 skill 等 CI。
8. **Ready for review 由使用者決定**，不要自己轉，也不要自己合併。
