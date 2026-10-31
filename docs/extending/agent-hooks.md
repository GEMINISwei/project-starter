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
`.codex/hooks.json` 的頂層只能有 `hooks`：多一個欄位（例如拿來寫註解的 `description`），Codex 就整份解析失敗、
所有 hook 都不載入，而且只在 `hooks/list` 留下警告，說明一律寫在這份文件（測試擋）。

## 目前有的 hook

| 腳本 | 事件 | 擋什麼 |
|---|---|---|
| `guard_commands.py` | `PreToolUse`（shell 指令） | push 到 `main`、用 `--no-verify` 略過 git hook（`commit -n` 也算）、改 `core.hooksPath`、`gh pr merge`、`npm` 的 `--force`／`--legacy-peer-deps`、直接下 `docker compose`、繞過確認自己放行測試檔 |
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

開新專案（或換一台電腦）時照這份做一次。每一項少了都**不會報錯**，只是那一層檢查安靜地不生效。
標「init 檢查」的由 `make init dev` 擋下或提醒（`scripts/lib/agent_setup.sh`），其餘讀不到狀態，init 結束時會印出來提醒。
部署主機（`make init prod`）不跑 agent，不需要這些。


- [ ] **`make init dev`**（init 設定）：把 `core.hooksPath` 設成 `.githooks`，commit-msg 才會檢查 `Co-authored-by`。
  已經 clone 的重跑一次即可；沒設時 `make check` 會提醒。
- [ ] **PATH 上有 `python3` 3.9 以上**（init 檢查，沒有就擋）：hook 直接用它執行（macOS 內建的 3.9 即可）。
  沒有的話 Claude 只顯示 hook 錯誤、照常執行指令，等於沒有守衛。
- [ ] **Claude**：第一次開啟專案時確認信任，`.claude/settings.json` 的 hook 與權限、`.claude/skills` 才會載入。
  Claude Code 自己會設 `AI_AGENT`，不用另外設定。
- [ ] **Codex**（init 檢查：裝了 Codex 卻還沒信任時提醒）：信任專案的 `.codex/`，`config.toml`（設定 `AI_AGENT`）、`hooks.json` 與 `rules/` 才會載入；
  再用 `/hooks` 逐一確認每個 hook。hook 內容改了要重新確認。
- [ ] **Windows**：先 `git config --global core.symlinks true`（並開啟開發人員模式）再 clone，
  `.claude/skills` 才會是 symlink；否則 Claude 讀不到任何 skill（init 檢查，不是 symlink 就擋）。

裝好之後，請 agent 執行 `docker compose version` 確認會被指令守衛擋下。
選這個指令是因為 hook 沒生效時它也只是印出版本，不會造成任何影響。

要關掉：Claude 在 `.claude/settings.local.json`（不進版控）設 `"disableAllHooks": true`；
Codex 在自己的設定 `[features]` 設 `hooks = false`。git hook 用 `git config --unset core.hooksPath`。
