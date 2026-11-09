# AI agent 的 skills

Skill 是給 agent 的**流程**：一個資料夾一份 `SKILL.md`，平常只載入名稱與描述，任務符合時才讀全文。
Claude 與 Codex 用同一種格式（Agent Skills），只維護一份：

```text
.agents/skills/<name>/SKILL.md       ← 唯一的正本（Codex 讀這裡）
.claude/skills → ../.agents/skills   ← 整個目錄一條 symlink（Claude 讀這裡）
```

新增 skill 只要在 `.agents/skills/` 加資料夾，兩家開新 session 就看得到。symlink 由 git 保存（clone 與
「Use this template」都會帶著），Windows 要先 `git config core.symlinks true`。

該寫成 skill 的：多步驟、要判斷的流程（開 PR、等 CI、新增 migration、發版）。隨時要遵守的規則放 `AGENTS.md`，
參考資料放 `docs/`。skill 不是程式碼產生器。

## 寫法

- **只寫步驟**，用祈使句；理由只在不寫會做錯的地方留一句，細節連回 `docs/`，不複製（[starter/0011](../starter/0011-agent-guardrails-by-judgment.md)）。
- **frontmatter 只依賴 `name` 與 `description`**：`name` 與資料夾同名（小寫英數與 `-`）；`description` 一行，
  開頭講清楚什麼時候用，兩家靠它決定要不要載入。
- **不寫某一家專屬的工具或語法**：寫「在背景等 CI 跑完」，不寫工具名稱，不用 `$ARGUMENTS`（測試擋）。
- **固定的步驟寫成腳本**放在 skill 的 `scripts/`（`make check lint` 跑 shellcheck），要判斷的才寫成文字。
- **連結用相對路徑**指回 `docs/`（`../../../docs/…`），CI 檢查連結有效。

## 只能手動呼叫

會造成外部影響（發版會部署）、要由使用者起頭（移植哪個 repo 的 PR）或一次耗用很多資源（`project-review` 派出多個 subagent）的流程，要關掉自動觸發，兩家各一個設定，一起設：

| | 設定 |
|---|---|
| Claude | `SKILL.md` 的 frontmatter 加 `disable-model-invocation: true` |
| Codex | `agents/openai.yaml` 寫 `policy:` → `allow_implicit_invocation: false` |

例見 `.agents/skills/release/`。只設一邊時 CI 擋（`apps/api/tests/test_agent_skills.py`）。
兩邊都忘了也算「一致」，所以影響 repo 以外的 skill 另外列在同一份測試的 `EXTERNAL_EFFECT_SKILLS`，要求一定是手動；
新增這類 skill 時把名字加進去。
