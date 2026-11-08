# 0010. 部署不設 environment reviewer，由發布前的確認把關

狀態：採用（2026-11-08）

## 背景

部署在發布 release 時觸發，發布由 agent 經 `release` skill 執行。主流做法是 environment 設
**Required reviewers**，這是唯一由 GitHub 強制、agent 繞不過的關卡。但這個 repo 只有一位維護者，
與 agent 用同一個 GitHub 帳號；`deploy.yml` 有兩個 job 進 environment，多套系統時每輪都要逐一放行，太繁瑣。

## 決定

不設 Required reviewers。發布前由 agent 這一側確認：`release` skill 先用 `preview.sh` 給使用者看，
使用者在對話裡同意後才執行固定寫法的 `publish.sh`，兩家的設定都讓它跳確認；hook 擋下其他會部署的常見寫法
（[說明](../extending/agent-hooks.md#發布-release)）。

## 後果

- 發布前在對話裡確認一次就好。
- 防線只在 agent 這一側：換寫法（例如 `curl` 直接打 API）或 hook 沒載入時擋不住，也沒有提示。
- agent 在無人看著的情況下執行（雲端、排程）、有第二位維護者，或 agent 改用自己的帳號或 token 時，
  改回設定 Required reviewers。
