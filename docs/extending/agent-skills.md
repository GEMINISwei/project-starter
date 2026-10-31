# AI agent 的 skills

Skill 是給 AI agent 的**流程**：一個資料夾放一份 `SKILL.md`，平常只載入名稱與描述，任務符合時才讀完整內容。
Claude 與 Codex 用同一種格式（Agent Skills），所以這個 repo 只維護一份：

```text
.agents/skills/<name>/SKILL.md   ← 唯一的正本（Codex 直接讀這裡）
.claude/skills → ../.agents/skills   ← 整個目錄一條 symlink（Claude 讀這裡）
```

新增 skill 只要在 `.agents/skills/` 加一個資料夾，兩家開新的 session 就看得到，不用再碰 symlink。
symlink 由 git 保存，clone 與「Use this template」都會帶著；Windows 要先 `git config core.symlinks true`。

什麼該寫成 skill：多個步驟、需要判斷的流程（開 PR、等 CI、新增 migration、發版）。
隨時都要遵守的規則放 `AGENTS.md`，參考資料放 `docs/`；skill 只寫步驟，細節連回文件，不要複製一份。
它不是程式碼產生器，不產生模組的檔案結構。

## 寫法

- **frontmatter 只依賴 `name` 與 `description`**：`name` 與資料夾同名（小寫英數與 `-`），
  `description` 寫一行，前面就講清楚「什麼時候用」，兩家都靠它決定要不要載入。
- **內文不寫某一家專屬的工具或語法**：寫「在背景等 CI 跑完」，不寫某一家的工具名稱；不用 `$ARGUMENTS`。
- **步驟固定的部分寫成腳本**，放在 skill 的 `scripts/`（`make check lint` 會跑 shellcheck），
  需要判斷的部分才寫成文字。
- **連結用相對路徑**指回 `docs/`（`../../../docs/…`），`make check` 會檢查連結有效。

## 只能手動呼叫

會造成外部影響的流程（例如發版會觸發部署）要關掉自動觸發，兩家各一個設定，要一起設：

| | 設定 |
|---|---|
| Claude | `SKILL.md` 的 frontmatter 加 `disable-model-invocation: true` |
| Codex | `agents/openai.yaml` 寫 `policy:` → `allow_implicit_invocation: false` |

例見 `.agents/skills/release/`。只設一邊時 `make check` 會擋（`apps/api/tests/test_agent_skills.py`）。
