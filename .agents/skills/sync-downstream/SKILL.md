---
name: sync-downstream
description: 把 project-starter 的修正同步到由它建立的子專案時使用。會改別的 repo，只在使用者明確要求時使用。
disable-model-invocation: true
---

# 同步到子專案

子專案是用「Use this template」從這個 repo 建立的，沒有共同的 git 歷史，只能逐個 commit 移植。
未經驗證的改法不能擴散出去，所以**一定先在 starter 驗證完，才動子專案**。

## 1. 確認 starter 這一側已經完成

- 要同步的修正已經合併進 starter 的 `main`，CI 全綠
- 驗證是在 starter 做的：子專案已經有類似的修法、或在子專案試過可行，都不能代替
- 還沒合併或還沒驗證完的，停下來告訴使用者，不要先動子專案

## 2. 列出要同步的內容

列給使用者確認之後才開始：

- 子專案的路徑與 repo
- 要同步的 starter commit（`git log --oneline` 的短 hash 與標題）
- 每個 commit 在子專案會碰到的檔案，以及子專案自己改過、可能衝突的地方

不同步模板 repo 專屬的內容：版本號、`CHANGELOG.md` 的條目、只對 starter 有意義的文件。

## 3. 在子專案照它自己的流程做

子專案有自己的 `AGENTS.md` 與流程，以它的為準（開分支、Draft PR、驗收條件、測試、`make check`）。

- 一次同步一個主題，一個 PR
- 移植時對照 starter 的 diff，不要憑印象重寫
- 子專案的 migration 是獨立的：starter 的 migration 不能直接複製，要在子專案另外產生

## 4. 回報

- 每個 commit 是否已同步、在子專案的 PR
- 子專案與 starter 不同、需要另外處理的地方
