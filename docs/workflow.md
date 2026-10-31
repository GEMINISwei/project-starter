# 開發流程與提交

## 開發流程

每個改動都走同一條路，`main` 只透過 PR 前進：

```text
Feature Branch → Draft PR → Incremental Commits → Code Review → Squash Merge
```

1. **Feature Branch**：從最新的 `main` 開分支，命名 `<type>/<kebab-case>`（`feat/product-list`）。
   不直接 push `main`。一個分支只做一件事，做到一半發現別的問題就另開分支，不要順手塞進來。
2. **Draft PR**：分支第一次 push 就開 Draft PR（`gh pr create --draft`），先照模板寫「摘要」與
   [驗收條件](testing.md#驗收條件與測試名稱)。動手前就把方向攤開，方向錯了在寫程式之前就會被看到。
   描述固定三段（[模板](../.github/PULL_REQUEST_TEMPLATE.md)）；`gh pr create --body` 會跳過模板，
   自己帶內文時照同樣三段寫：
   - **摘要**：改了哪些內容、為什麼。之後再推 commit 時回來補，讓它一直對得上最新的 diff。
   - **驗證**：做過哪些驗證與結果，**成功與失敗都寫**，沒驗到的寫原因。
   - **檢查**：請審查者確認的項目，用 checkbox 列。整份 diff 本來就要看，不用列；這裡只寫
     diff 看不出來、要有人去確認的事（例：在部署主機實際跑一次、對已部署的下游有沒有影響）。
3. **Incremental Commits**：小步提交、常常 push，每個 commit 是一個說得清楚的步驟
   （例：先補測試、再實作、再整理）。這些 commit 的訊息會併進 squash 後的內文，所以寫成
   「做了什麼、為什麼」，不要一路 `wip`、`fix`。
4. **Code Review**：`make check` 綠、「驗證」寫完、整份 diff 自己讀過一次，才按
   **Ready for review**。回應 review 用新的 commit，不要 force push 改寫已經被看過的歷史，
   reviewer 才看得出這一輪改了什麼。CI 綠、意見都處理完才合併。
5. **Squash Merge**：一律 **Squash and merge**，`main` 上一個 PR 一個 commit。squash 後的標題就是
   `main` 的 commit 標題，所以 **PR 標題**要符合下面的 commit 格式。合併後刪除分支。

GitHub 端要設定一次，流程才不是靠自覺：

- [ ] Settings → General → Pull Requests：只勾 **Allow squash merging**，預設訊息選
  **Pull request title and commit details**，並勾 **Automatically delete head branches**
- [ ] Settings → Rules：替 `main` 建 ruleset，開下面幾項。上一項的 General 設定任何管理員都能改回來，
  而且不會有人發現；ruleset 綁在 `main` 上，才是真正擋住的那一層：
  - **Restrict deletions**、**Block force pushes**：建 ruleset 時預設勾起，保持勾選
  - **Require linear history**：`main` 上不會出現 merge commit，有 bypass 權限的人直接 push 也一樣
  - **Require a pull request before merging**，展開後把 **Allowed merge methods** 改成只留 **Squash**
  - **Require status checks to pass**：把 CI 的四個 job（`check`、`integration`、`images`、`e2e`）
    與 PR 格式檢查的 `pr`（`.github/workflows/pr.yml`）加進去，並勾 **Require branches to be up to date before merging**，CI 是跟最新的 `main` 一起跑過的。
    CI 多了 job 時要回來這裡加：沒列進去的 job 紅了，PR 照樣能合併
- [ ] Settings → Advanced Security（有的帳號叫 Code security）：三項都要打開，少一項安全更新就不會來
  （套件只收安全更新，見〈相依升級〉）：
  - **Dependency graph**：從 lock 檔與 manifest 解析出相依清單，後兩項都靠它
  - **Dependabot alerts**：拿相依清單比對漏洞資料庫，有漏洞時在 Security 分頁發警示
  - **Dependabot security updates**：針對警示自動開升級到修補版的 PR

## 提交與 CI

- PR 標題與 commit：[Conventional Commits](https://www.conventionalcommits.org/zh-hant/v1.0.0/)，
  `<type>: <祈使句>`（`feat: add product list page`）。PR 標題是硬規定（squash 後留在 `main`），
  分支上的 commit 建議照寫。PR 標題與描述的三段由 `pr.yml` 檢查，在 GitHub 上修改標題或描述也會重跑。
- 送出前通過 `make check`，實質改動在 [`CHANGELOG.md`](../CHANGELOG.md) 的 `## [Unreleased]` 留一筆。

CI（`.github/workflows/ci.yml`）跑的就是本機指令：`check`（`make check`，含契約比對）、`integration`（`make check integration`）、`images`（兩份 production image
建得起來，且 web image 裡沒有真的 Server Action 金鑰）、`e2e`（`make check e2e`）。**本機綠，CI 就綠。** 部署另由
`deploy.yml` 在 Publish release 時執行，見 [`operations.md`](operations.md#自動部署)。

### AI 協作的共同作者

AI 參與產生的 commit 一律在訊息最後加上 `Co-authored-by`，之後看 history 才知道哪些改動是哪家的
AI、哪個模型做的：

```text
feat: add product list page

列表改用游標分頁, 資料量成長後 offset 會越來越慢。

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>
```

- **名稱寫到模型與版本**（`Claude Opus 5.5`），不要只寫廠商或工具名：同一家的不同模型能力差很多，
  回頭追問題時要分得出來。
- **email 用工具官方設定的值**，工具沒有提供時用 `noreply@<廠商網域>`。這類位址沒有對應的 GitHub 帳號，
  GitHub 上只顯示成文字、不會連到頭像，紀錄的作用一樣在。
- trailer 放在訊息最後，前面空一行，一位共同作者一行；同一個 commit 有多個 AI 參與就各寫一行。
- **AI agent 做的 commit 由 `.githooks/commit-msg` 檢查**：`AI_AGENT` 環境變數有值時（跨工具的慣例，
  Claude Code 自己會設，Codex 由專案的 `.codex/config.toml` 補上），沒有 trailer、或名稱沒寫到版本就擋下。
  人自己 commit 不檢查。git hook 要 `make init dev` 設定 `core.hooksPath` 才會生效（已經 clone 的重跑一次），
  沒設時 `make check` 會提醒。squash 時 GitHub 會把分支上的 trailer 帶進 `main` 的內文，合併時不要把它們刪掉。

查某段期間各 commit 的共同作者：

```bash
git log --format='%h %s%n  %(trailers:key=Co-authored-by,valueonly,separator=%x2C )'
```

### 相依升級

系統上線後**不追最新版，只在有漏洞時升**（`.github/dependabot.yml`）：

- **套件與 GitHub Actions**：Dependabot 只開安全更新，一般的版本更新關掉了。要在 repo 的
  Settings 打開 Dependency graph、Dependabot alerts 與 security updates 才會運作，警示在 Security 分頁。
- **Docker image**：漏洞資料庫不涵蓋 image，所以每月開一次 PR，只送 patch（例如 nginx 1.31.7 → 1.31.8）。
- **整批升級**：在發版前盤點落後多少再決定範圍——開分支、升級、`make check`、實際建置 image 跑起來，
  再開 PR。api Dockerfile 用 `COPY --from` 複製的 uv 不在 Dependabot 的範圍內，盤點時要用
  `docker scout` 之類的工具掃 image 才看得到。Insights → Dependency graph → Dependabot 的
  「Check for updates」在版本更新關掉後不會開 PR，不能拿來取代盤點。

遇到 peer 相容性阻擋就**停在最新的相容版**，不要 `--force`／`--legacy-peer-deps`，並在設定檔裡
寫下「為什麼停」與「移除條件」。目前：ESLint 停在 9.x（見 `eslint.config.mjs`）、TypeScript 停在
5.x（見 `package.json` 的 `//devDependencies`），兩者在 `dependabot.yml` 也 ignore 了 major，
移除條件成立時兩邊一起拿掉。

