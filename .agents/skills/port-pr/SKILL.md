---
name: port-pr
description: 把別的 repo 已合併的 PR 移植到這個 repo 時使用。一次執行整理成這邊的一個 PR。只在使用者明確要求時使用。
disable-model-invocation: true
---

# 移植別的 repo 的 PR

兩個 repo 沒有共同的 git 歷史時，不能 merge 或 cherry-pick，只能對照來源的 diff 移植。
要參考哪個 repo、哪幾個 PR 由使用者決定，這裡只負責引導。

## 1. 問來源

- 要參考哪個 repo（`owner/name`）
- 要移植哪幾個 PR。使用者還沒決定時，可以列出那個 repo 最近合併的 PR 給他挑：

  ```bash
  gh pr list --repo <repo> --state merged --limit 30 --json number,title,url,mergedAt
  ```

## 2. 逐個看過，給使用者確認

每個 PR 讀描述與 diff（`gh pr view <編號> --repo <repo>`、`gh pr diff <編號> --repo <repo>`），列出：

- 這個 PR 改了什麼、為什麼
- 這邊會碰到的檔案，以及這邊自己改過、可能衝突的地方
- 這邊是否已經有了：把 patch 存成暫存檔，`git apply -R --check <patch>` 能過就代表已經套用過，提醒使用者可以跳過

不帶過來的：來源 repo 自己的版本號、`CHANGELOG.md` 的條目、只對來源 repo 有意義的文件。
**使用者確認要移植哪些之後才動手。**

## 3. 整理成一個 PR

這次選定的全部放進一個分支、一個 PR，照這個 repo 的 `AGENTS.md` 與流程做（開分支、Draft PR、驗收條件、測試、`make check`）。

- 所有來源 PR 的驗收條件與測試先寫、先 commit，全部寫完才開始實作。照來源 PR 逐個「測試、實作」交錯 commit 的話，
  第二個來源 PR 的測試會落在實作之後，被當成實作後改測試
- commit 與 PR 用這個 repo 自己的話寫改了什麼、為什麼，不寫來源 repo 的名稱或網址；來源 PR 只在回報時列給使用者
- 對照來源的 diff 移植，不要憑印象重寫
- migration 是各自獨立的：來源的 migration 不能直接複製，要在這邊另外產生

## 4. 回報

- 每個來源 PR：已移植、跳過（附理由）
- 這邊與來源不同、需要另外處理的地方
