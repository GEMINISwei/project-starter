# AI agent 的 hooks

Hook 是 agent 每次呼叫工具之前（或之後）執行的指令，可以擋下這次呼叫。這個 repo 用它擋下
規則明文禁止、但 git 與 CI 看不到的事：agent 在 session 裡執行的指令。

**它是第一道防線，不是安全機制。** 指令換個寫法就可能繞過，真正擋得住的是 git 與 CI；
hook 的價值是讓 agent 在動手的當下就停下來，而不是等到 CI 紅了才回頭。

## 結構

Claude 與 Codex 的 hook 協定相同（事件名稱、stdin 收的 JSON、回傳 `permissionDecision` 的格式），
所以邏輯只寫一份，設定各一份、只負責呼叫：

```text
.agents/hooks/<name>.py     ← 唯一的邏輯（Python 標準函式庫，不必先裝相依）
.claude/settings.json       ← Claude 的設定，呼叫時帶 claude
.codex/hooks.json           ← Codex 的設定，呼叫時帶 codex
```

設定檔不共用：`.claude/settings.json` 同時是 Claude 的整份專案設定（權限等），格式跟 Codex 的不同。
兩份呼叫的事件、matcher 與腳本必須一致，只有參數不同（`apps/api/tests/test_agent_hooks.py` 擋）。
參數留給兩家行為不同的地方，例如 Codex 的 `PreToolUse` 不支援 `ask`。

## 目前有的 hook

| 腳本 | 事件 | 擋什麼 |
|---|---|---|
| `guard_commands.py` | `PreToolUse`（shell 指令） | push 到 `main`、`gh pr merge`、`npm` 的 `--force`／`--legacy-peer-deps`、直接下 `docker compose` |

## 新增一個 hook

1. 先在 `apps/api/tests/test_agent_hooks.py` 寫測試：用 subprocess 餵 JSON 進腳本，兩家各跑一次。
2. 在 `.agents/hooks/` 寫腳本：放行就什麼都不印；要擋就印出
   `{"hookSpecificOutput": {"hookEventName": …, "permissionDecision": "deny", "permissionDecisionReason": …}}`。
   理由寫成 agent 看得懂、知道下一步該怎麼做的句子，它會照著做。
3. 兩份設定各加一段，呼叫寫法固定為
   `python3 "$(git rev-parse --show-toplevel)/.agents/hooks/<name>.py" <claude|codex>`。

只放守**這個模板本身的規則**、很少誤擋、跑得快的 hook。格式化、自動跑檢查這類偏好，由繼承的專案自己加。

## 啟用與停用

- **Claude**：開啟專案時確認信任即生效。
- **Codex**：專案的 `.codex/` 要先被信任，再用 `/hooks` 逐一確認每個 hook；hook 內容改了要重新確認。
  沒有信任時專案的 hook **不會載入，也不會報錯**。
- 要關掉：Claude 在 `.claude/settings.local.json`（不進版控）設 `"disableAllHooks": true`；
  Codex 在自己的設定 `[features]` 設 `hooks = false`。
