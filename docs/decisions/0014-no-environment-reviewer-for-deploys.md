# 0014. 部署不設 environment reviewer，由發布前的確認把關

狀態：採用（2026-11-08）

## 背景

部署在 GitHub 上發布 release 時觸發，發布由 AI agent 經 `release` skill 執行。要確保「沒有使用者點頭，
正式環境就不會變」，主流做法是在 environment 設 **Required reviewers**：deploy workflow 跑到進
environment 的 job 時暫停，等人在 GitHub 上按 Approve。這是唯一由 GitHub 強制、agent 繞不過的做法。

這個 repo 只有一位維護者與 agent，用的是同一個 GitHub 帳號。`deploy.yml` 有兩個 job 進 environment
（`migration-check` 與 `deploy`，先後執行），所以每次部署要按兩次 Approve；`production-*` 有多套系統時，
要在每一輪等待裡逐一放行。發布前在對話裡確認過一次，之後在 GitHub 上再按兩次，實際使用時太繁瑣。

## 決定

不設 Required reviewers。「發布一定先經過使用者確認」由 agent 這一側把關：

- `release` skill 先用 `preview.sh` 列出要發布的內容，使用者在對話裡同意後，才執行固定寫法的 `publish.sh`；
  兩家的設定都讓這個指令一定跳確認（[說明](../extending/agent-hooks.md#發布-release)）。
- `guard_commands.py` 擋下其他會部署的寫法：`gh release create/edit/delete`、`gh workflow run deploy…`、
  `gh api` 動到 release 或觸發 workflow、重跑 Deploy 的 run。

## 後果

- 部署不用在 GitHub 上另外按 Approve，發布前在對話裡確認一次就好。
- 防線只在 agent 這一側。hook 擋的是已知的寫法：用 `curl` 帶 token 直接打 GitHub API、或 hook 沒有載入
  （專案沒被信任、`python3` 不在 PATH）時擋不住，而且不會有任何提示。
- 有下面任何一種情況時，應該改回設定 Required reviewers：agent 在沒有人看著的情況下執行（雲端、排程）、
  有第二位維護者、或 agent 改用自己的 GitHub 帳號或 token（那時 GitHub 才分得出是誰發布的）。
