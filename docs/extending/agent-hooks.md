# AI agent 的 hooks

Hook 在 agent 呼叫工具前後執行，可以擋下這次呼叫。這裡只擋**確認點**：不可逆、碰到 `main` 或正式環境的動作，
而且只認常見寫法。其餘交給 agent 依 `AGENTS.md`〈高風險先問〉判斷，換寫法擋不住是已知的取捨，
由 CI 與審查補（[ADR 0011](../decisions/0011-agent-guardrails-by-judgment.md)）。

## 結構

```text
.agents/hooks/<name>.py   ← 唯一的邏輯（Python 標準函式庫）
.claude/settings.json     ← Claude 的設定，呼叫時帶 claude
.codex/hooks.json         ← Codex 的設定，呼叫時帶 codex
.codex/rules/             ← Codex 的確認（它的 hook 不支援 ask）
```

- 兩份設定呼叫的事件、matcher、腳本要一致，只有參數不同（`test_agent_hooks.py` 擋）。
- `.codex/hooks.json` 頂層只能有 `hooks`：多一個欄位，Codex 就整份不載入，只留警告（測試擋）。

## 目前有的 hook

| 腳本 | 事件 | 做什麼 |
|---|---|---|
| `guard_commands.py` | `PreToolUse`（shell） | **deny**：push 到 `main`（`--dry-run` 不算）、`--no-verify`／`commit -n`、改 `core.hooksPath`、`gh pr merge`／`gh pr ready`、`gh release create/edit/delete`、`gh workflow run deploy…`、不經固定寫法執行 `publish.sh`、自己寫放行<br>**確認**：`publish.sh`、`gh api` 用 GET 以外的方法（GraphQL 看有沒有 `mutation`）、`gh run rerun`、有開著的 PR 時開新分支 |
| `guard_tests.py` | `PreToolUse`（改檔工具） | **確認**：實作開始後改測試檔、改防線檔案；**deny**：直接改放行檔 |
| `require_check.py` | `Stop` | 改過的程式還沒跑過 `make check` 就要求先跑 |
| `session_context.py` | `SessionStart` | 不擋，把分支、開著的 PR、測試鎖狀態加進上下文 |

`bash -c`、`eval` 的內容會展開來看，heredoc 的內容當成資料不看。

## 確認的方式

| | 怎麼確認 |
|---|---|
| Claude | hook 回 `ask`，畫面直接跳確認 |
| Codex | hook 回 `deny`。要放行的（測試檔、防線檔案、插隊的分支）由 agent 說明後執行 `python3 .agents/hooks/approve.py <test\|protected\|branch> <路徑或分支…>`，`.codex/rules/approve.rules` 讓它跳確認；其餘（`gh api` 寫入、重跑 run）請使用者自己執行 |

放行寫在 `.git/agent-approvals`（不進版控）：測試檔與防線檔案的放行**只在目前的 HEAD 有效**，有新 commit 就失效；
分支的放行針對名稱，之後開 PR 不再問。直接寫放行檔、換寫法執行 `approve.py` 會被擋。

## 測試鎖定

[`testing.md`](../testing.md#改程式不改測試)〈改程式不改測試〉在 agent 這一側的檢查：

- **測試檔**：`apps/*/tests/**`、`e2e/tests/**`，輔助檔與資料也算（`test_lock.py`）。
- **實作開始了**：分支相對 `origin/main`（含未 commit 與未追蹤）改了 `apps/`、`e2e/`、`.agents/hooks/`、
  `.github/scripts/`、`scripts/` 底下的非測試、非 Markdown 檔案。CI 的 `pr` 用同一個判斷。
- 只攔改檔工具。用 shell 改測試檔不攔，由 CI 的 `pr` 要求在「驗證」段寫出改過的測試檔。

## 防線檔案

決定其他檢查擋不擋得住的檔案，用改檔工具改之前一律確認，不分實作前後（清單在 `protected_files.py`）：

| 類別 | 路徑 |
|---|---|
| agent 的 hook 與設定 | `.agents/hooks/`、`.claude/`（含 `settings.local.json`）、`.codex/` |
| git hook | `.githooks/` |
| CI | `.github/workflows/`、`.github/scripts/` |
| 檢查的設定 | `apps/api/pyproject.toml`、`apps/web/package.json`、`eslint.config.mjs`、`.dependency-cruiser.cjs`、`knip.ts`、`tsconfig.json`、`vitest.config.ts` |
| 檢查的入口 | `scripts/check.sh`、`Makefile` |

- 改了不會有檢查變紅（刪掉 CI 步驟照樣綠燈、`disableAllHooks` 讓 hook 安靜失效），所以要讓使用者看到。
- 用 shell 改不攔；CI 的 `pr` 要求動到的防線檔案列進 PR 的「檢查」段。
- 刻意不保護：`AGENTS.md`、`docs/`、`.agents/skills/`、PR 模板（CI 一樣要求列進「檢查」段）。

## 一次一個 PR

[`workflow.md`](../workflow.md#一次一個-pr)〈一次一個 PR〉：還有自己開著的 PR（`gh pr list --author @me`）時，
開新分支（`git switch -c`、`git checkout -b`、`git branch <名稱>`）、`git worktree add`、`gh pr create` 要確認。
查不到 PR（沒網路、沒登入）時放行。

## 收尾前的 make check

`make check`（不帶參數）全部通過時，`scripts/check.sh` 呼叫 `check_stamp.py record`，把工作目錄的內容
（不含 Markdown）記成 git tree。收尾時分支有非 Markdown 的改動、而且內容跟紀錄不同，就要求先跑 `make check`。
同一輪被要求過一次就放行（`stop_hook_active`），agent 停下來可能只是要問問題。

## 開工時的現況

開新 session、恢復或壓縮上下文後，把目前分支、開著的 PR、測試鎖狀態與插隊放行的分支加進上下文。

## 發布 release

發布會直接部署，只能用固定寫法 `.agents/skills/release/scripts/publish.sh`，兩家都一定跳確認
（Claude 的 `permissions.ask` 與 hook、Codex 的 `.codex/rules/publish-release.rules`）。GitHub 端刻意不設
environment reviewer，這裡是部署前唯一的確認（[ADR 0010](../decisions/0010-no-environment-reviewer-for-deploys.md)）。

## 新增一個 hook

1. 先在 `apps/api/tests/` 寫測試：用 subprocess 餵 JSON 進腳本，兩家各跑一次。
2. 腳本要能在 Python 3.9 上跑（PATH 上的 `python3`，macOS 內建 3.9）：加 `from __future__ import annotations`。
   放行什麼都不印；要擋就印 `hookSpecificOutput.permissionDecision`，理由寫成 agent 知道下一步的句子。
3. 兩份設定各加一段：`python3 "$(git rev-parse --show-toplevel)/.agents/hooks/<name>.py" <claude|codex>`。

只放確認點、很少誤擋、跑得快的 hook。格式化、自動跑檢查這類偏好由繼承的專案自己加。

## 啟用與停用

少了任何一項都**不會報錯**，只是那一層安靜地不生效。標「init 檢查」的由 `make init dev` 擋下或提醒。

- [ ] **`make init dev`**：把 `core.hooksPath` 設成 `.githooks`，commit-msg 才會檢查 `Co-authored-by`。
- [ ] **PATH 上有 `python3` 3.9 以上**（init 檢查）：沒有的話 hook 只顯示錯誤、照常執行，等於沒有守衛。
- [ ] **Claude**：信任專案，`.claude/settings.json` 與 `.claude/skills` 才會載入。Claude Code 自己會設 `AI_AGENT`。
- [ ] **Codex**（init 檢查）：信任專案的 `.codex/`，`config.toml`（設 `AI_AGENT`）、`hooks.json`、`rules/` 才會載入；
  用 `/hooks` 逐一確認，hook 改了要重新確認。
- [ ] **Windows**：先 `git config --global core.symlinks true` 再 clone，`.claude/skills` 才是 symlink（init 檢查）。

裝好後請 agent 執行 `gh pr merge 0` 確認被擋下（hook 沒生效時它也只會因為找不到 PR 而失敗）。

要關掉：Claude 在 `.claude/settings.local.json` 設 `"disableAllHooks": true`；Codex 在設定的 `[features]` 設
`hooks = false`；git hook 用 `git config --unset core.hooksPath`。
