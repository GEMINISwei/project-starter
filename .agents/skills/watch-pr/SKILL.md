---
name: watch-pr
description: 開好或更新 PR 之後使用：在背景等 CI 跑完並回報結果，使用者合併（或關閉）PR 之後把本機同步回 main 並清掉分支。
---

# 等 CI、合併後同步本機

兩件事都要在背景執行、完成時通知的方式等，不要反覆執行指令去問狀態。

## 1. 等 CI 跑完

```bash
gh pr checks <PR 號碼> --watch --fail-fast
```

跑完回報每個 job 的結果。失敗時用 `gh run view <run id> --log-failed` 讀失敗的那一段，說明原因；
要不要修、怎麼修先問使用者。

## 2. 等 PR 關閉，再同步本機

轉成 Ready for review 與合併都由使用者做，不要自己合併。同時在背景執行：

```bash
.agents/skills/watch-pr/scripts/wait-pr-closed.sh <PR 號碼>
```

它在 PR 不再是 `OPEN` 時結束，印出 `MERGED` 或 `CLOSED`。之後不用再問使用者，直接：

1. `git switch main && git fetch --prune && git pull --ff-only`
2. `MERGED`：刪掉本機的分支。squash merge 後 git 認不出它已合併，要用 `git branch -D`，
   所以一定先確認狀態是 `MERGED` 才刪。`CLOSED`（沒合併）：保留分支並回報。
3. 確認 `main` 與 `origin/main` 是同一個 commit，回報那個 commit。
4. 這次合併改到 `uv.lock` 或 `package-lock.json` 時，提醒要重裝相依（`apps/api` 跑 `uv sync`，`apps/web`、`e2e` 跑 `npm ci`）。
