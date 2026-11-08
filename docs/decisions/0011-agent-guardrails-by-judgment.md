# 0011. agent 防線以判斷為主，hook 只擋確認點

狀態：採用（2026-11-08）

## 背景

模板曾用 hook 逐一解析 shell 寫法（重新導向、`python -c`、patch、`gh api` 端點……）來擋 agent 繞過規則。
每補一種寫法就出現下一種，守衛與它的測試越來越大，誤擋也跟著變多；而每個專案的風險點不同，這種清單不可能完整。
主流的 agent 工具（Claude、Codex）都已能讀懂規則、判斷風險，並在不確定時停下來問。

同一個 repo 同時給 Claude 與 Codex 用：`AGENTS.md` 與 Agent Skills 是兩家共通的格式，hook 則沒有標準，
只是協定剛好相近（Codex 的 `PreToolUse` 不支援 ask）。

## 決定

- **三層防線**：
  1. 硬底線交給 git、CI 與 GitHub ruleset（`main` 只經 PR、required checks、commit-msg）。
  2. hook 只擋**確認點**：不可逆、碰到 `main` 或正式環境的動作，只認最常見的寫法，回 deny 或 ask。
  3. 其餘由 agent 依 `AGENTS.md`〈高風險先問〉自己判斷，拿不準就問。
- **不追求繞不過**：換寫法擋不住是已知的取捨，由 CI 與審查事後補。不再為新的繞法擴充 hook。
- **文字寫給 agent 看**：`AGENTS.md`、skills、hook 的理由用祈使句，一條規則只寫一處，「為什麼」只在不寫會做錯時留一句。
- **Codex 的確認**：hook 回 deny，agent 向使用者說明後用唯一的申請指令 `approve.py` 申請，由 Codex rule 跳確認。
- **一個任務一個 agent**：Claude 與 Codex 可以互換，也可以交叉審查對方的 PR；不讓兩個 agent 同時改同一個分支。
  「一次一個 PR」維持不變。

## 後果

- hook 與它的測試大幅縮小，誤擋減少；繼承的專案依自己的風險調整〈高風險先問〉即可。
- agent 若判斷錯誤，會在 CI 或審查時才被發現，而不是動手當下。
- 測試鎖只攔改檔工具，用 shell 改測試檔要靠 agent 自律與 CI 的 `pr`。
- 需要多個 agent 平行開發時，要先改流程（一個任務一個 worktree、放行與檢查紀錄以 worktree 為單位），再重新檢討。
- agent 在無人看著的環境執行時，判斷層沒有人可以問，要改回較嚴格的 hook 或 GitHub 端的關卡
  （同 [0010](0010-no-environment-reviewer-for-deploys.md)）。
