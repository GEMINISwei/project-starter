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
| `guard_commands.py` | `PreToolUse`（shell 指令） | push 到 `main`、`gh pr merge`、`npm` 的 `--force`／`--legacy-peer-deps`、直接下 `docker compose`、繞過確認自己放行測試檔 |
| `guard_tests.py` | `PreToolUse`（改檔） | 實作開始後改測試檔，見下一節 |

## 測試鎖定

把 [`testing.md`](../testing.md#改程式不改測試)〈改程式不改測試〉變成 agent 動手當下的檢查：

- **測試檔**：`apps/*/tests/**`、`e2e/tests/**`，輔助檔與資料也算（判斷在 `.agents/hooks/test_lock.py`）。
- **實作開始了**：分支相對 `origin/main` 的差異（含還沒 commit 與沒追蹤的）有 `apps/`、`e2e/` 底下的非測試檔案。
  只改文件或設定不算。不需要任何人標記，從 git 推導。
- **之後改測試檔要使用者同意**，兩家的方式不同：

| | 攔下 | 使用者怎麼同意 |
|---|---|---|
| Claude | hook 回 `ask` | 直接在這次修改的確認上按允許 |
| Codex | hook 回 `deny`（不支援 `ask`），理由裡請 agent 先說明再申請 | agent 執行 `python3 .agents/hooks/approve_test_edit.py <測試檔>`，`.codex/rules/approve-test-edit.rules` 讓它一定跳確認，按允許後再改就放行 |

放行寫在 `.git/agent-approved-test-edits`（不進版控），**只對列出的檔案、只在目前的 HEAD 上有效**，有新的 commit
就失效。申請指令的寫法固定：直接寫放行檔、換寫法執行申請指令都會被 `guard_commands.py` 擋下，否則就繞過了確認。
Claude 也能用同一個申請指令（`.claude/settings.json` 的 `permissions.ask` 讓它一樣要確認），但直接按允許比較方便。

agent 用 shell 指令（`sed -i`、重新導向）改測試檔時不會被攔：hook 只看改檔工具。

## 新增一個 hook

1. 先在 `apps/api/tests/test_agent_hooks.py` 寫測試：用 subprocess 餵 JSON 進腳本，兩家各跑一次。
2. 在 `.agents/hooks/` 寫腳本，**要能在 Python 3.9 上跑**（由 PATH 上的 `python3` 執行，macOS 內建的是 3.9）：
   開頭加 `from __future__ import annotations`，`.agents/hooks/ruff.toml` 把語法目標設在 3.9。
   放行就什麼都不印；要擋就印出
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
