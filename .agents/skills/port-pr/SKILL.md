---
name: port-pr
description: 把別的 repo 已合併的 PR 移植到這個 repo 時使用。一次執行整理成這邊的一個 PR。只在使用者明確要求時使用。
disable-model-invocation: true
---

# 移植別的 repo 的 PR

沒有共同 git 歷史，不能 merge 或 cherry-pick，只能對照來源的 diff 移植。來源由使用者決定。

1. **問來源**：哪個 repo（`owner/name`）、哪幾個 PR。還沒決定時列出最近合併的給他挑：
   `gh pr list --repo <repo> --state merged --limit 30 --json number,title,url,mergedAt`
2. **逐個看過，給使用者確認**：讀描述與 diff（`gh pr view`／`gh pr diff <編號> --repo <repo>`），列出改了什麼、為什麼，
   這邊會碰到的檔案與可能衝突的地方，以及是否已經有了（patch 存成暫存檔，`git apply -R --check` 能過就是已套用）。
   不帶過來：來源的版本號、CHANGELOG 條目、只對來源有意義的文件。**確認要移植哪些才動手。**
3. **整理成一個 PR**，照這個 repo 的流程（`feature-workflow`）：
   - 所有來源 PR 的測試先寫完、先 commit，才開始實作（交錯 commit 會被當成實作後改測試）
   - 用這邊自己的話寫 commit 與 PR，不寫來源 repo 的名稱或網址
   - 對照 diff 移植，不憑印象重寫；migration 在這邊另外產生
4. **回報**：每個來源 PR 已移植或跳過（附理由），以及這邊與來源不同、要另外處理的地方。
