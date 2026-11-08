---
name: sync-from-starter
description: 由 project-starter 建立的專案要把 starter 之後的修正（基礎建設、檢查、流程）同步進來時使用。只在使用者明確要求時使用。
disable-model-invocation: true
---

# 從 starter 同步修正

這個專案是用「Use this template」從 project-starter 建立的，兩邊沒有共同的 git 歷史，只能逐個 PR 移植。
starter 不知道有哪些專案繼承了它，所以由繼承的專案在需要時自己來拉。

## 1. 找到上游

```bash
gh repo view --json templateRepository --jq '.templateRepository // empty | "\(.owner.login)/\(.name)"'
```

- 沒有輸出時，可能是 project-starter 本身、或不是經 GitHub 的 template 建立的。是 starter 本身就告訴使用者
  這個 skill 是給繼承的專案用的，停下來；不是的話問使用者上游是哪個 repo

## 2. 列出還沒同步的 starter PR

每次同步的 commit 都會帶 `Starter-PR: <starter PR 的網址>` 的 trailer，squash 之後留在 `main` 的內文裡。
已經同步過的：

```bash
git log main --format='%(trailers:key=Starter-PR,valueonly)' | sort -u
```

候選是這個 repo 第一個 commit 之後 starter 合併、而且不在紀錄裡的 PR：

```bash
git log --reverse --format=%cs | head -1   # 這個 repo 建立的日期
gh pr list --repo <starter> --state merged --search "merged:>=<日期>" --limit 200 \
  --json number,title,url,mergedAt
```

只記已同步的，決定不同步的 PR 下次還會出現在清單裡，列的時候提醒使用者即可。

## 3. 給使用者挑

每個候選列出：PR 標題與網址、摘要（取 PR 描述的「摘要」段）、會碰到的檔案，以及這個專案自己改過、可能衝突的地方。
同一個主題的幾個 PR 可以合在一起列。**使用者選好之後才開始動手。**

不同步模板專屬的內容：版本號、`CHANGELOG.md` 的條目、只對 starter 有意義的文件（例如 README 的「開新專案時」）。

## 4. 照這個專案自己的流程做

以這個專案的 `AGENTS.md` 與流程為準（開分支、Draft PR、驗收條件、測試、`make check`）。

- 一次同步一個主題、一個 PR
- 移植時對照 starter 的 diff（`gh pr diff <編號> --repo <starter>`），不要憑印象重寫
- migration 是各自獨立的：starter 的 migration 不能直接複製，要在這個專案另外產生
- 每個 commit 最後的 trailer 區塊加上對應的 `Starter-PR: <網址>`（一個 PR 一行），步驟 2 靠它判斷同步到哪裡

## 5. 回報

- 每個 starter PR 是否已同步、在這個專案的 PR
- 這個專案與 starter 不同、需要另外處理的地方
