# 開發流程與提交

從開分支到合併的流程、commit 與 CI、相依升級。測試的寫法見 [`testing.md`](testing.md)。

## 為什麼這樣設計

- **`main` 只透過 PR 前進，一律 squash**：`main` 一個 PR 一個 commit，PR 標題就是 commit 標題，history 讀得懂。
- **先開 Draft PR 寫驗收條件**：方向錯了在寫程式前就看得到。
- **一次一個 PR**：一次審一件事，diff 才小得好讀，也不會建立在沒審過的程式上（〈[一次一個 PR](#一次一個-pr)〉）。
- **GitHub 端用 ruleset 擋**：General 的設定任何管理員都能悄悄改回，流程不能靠自覺（〈[GitHub 設定](#github-設定)〉）。
- **完整的檢查只在 CI 跑**：合併與部署只認 CI 的結果，本機只跑寫測試時的那一項（〈[提交與 CI](#提交與-ci)〉）。
- **AI 的 commit 寫明模型與版本**：同一家的模型能力差很多，追問題時要分得出來（〈[AI 協作的共同作者](#ai-協作的共同作者)〉）。
- **相依只在有漏洞時升**：上線後不追最新版，升級只在有理由時做（〈[相依升級](#相依升級)〉）。

## 開發流程

`main` 只透過 PR 前進：

```text
Feature Branch → Draft PR → Incremental Commits → Code Review → Squash Merge
```

1. **Feature Branch**：從最新的 `main` 開 `<type>/<kebab-case>`（`feat/product-list`），不直接 push `main`。
   一個分支只做一件事，途中發現別的問題另開分支。
2. **Draft PR**：第一次 push 就開 Draft PR（`gh pr create --draft`），先寫「摘要」與
   [驗收條件](testing.md#驗收條件與測試名稱)，方向錯了在寫程式前就看得到。AI agent 的驗收條件**先給使用者確認才寫測試**。
   只改 Markdown 的 PR 不寫測試，驗收條件的寫法見同一個連結。
   描述固定三段（[模板](../.github/PULL_REQUEST_TEMPLATE.md)；`gh pr create --body` 會跳過模板，自己照三段寫）：
   - **摘要**：改了什麼、為什麼。推新 commit 時回來補，對上最新的 diff。
   - **驗證**：做過的驗證與結果，**成功失敗都寫**，沒驗到的寫原因。
   - **檢查**：請審查者確認的 checkbox，只寫 diff 看不出、要人去確認的事（例：在部署主機跑一次、對下游的影響）。

   CI 的 `pr` 另外檢查這個 PR 新增的抑制註解，同一行要寫理由（`.github/scripts/check-pr-changes.py`，
   [說明](development.md#抑制註解)）。實作後改的測試檔與動到的[防線檔案](extending/agent-hooks.md#防線檔案)
   不用另外列出，審查時看 diff 的檔案清單。
3. **Incremental Commits**：小步提交、常 push，一個 commit 一個說得清楚的步驟（先測試、再實作、再整理）。
   訊息會併進 squash 後的內文，寫「做了什麼、為什麼」，不要一路 `wip`、`fix`。
4. **Code Review**：CI 綠、「驗證」寫完、整份 diff 自己讀過（AI agent 照 `feature-workflow` 第 7 步）
   才按 **Ready for review**。回應 review 用新的 commit，不 force push 改寫看過的歷史。CI 綠、意見處理完才合併。
5. **Squash Merge**：一律 **Squash and merge**，`main` 一個 PR 一個 commit，標題就是 PR 標題，所以 PR 標題要符合
   下面的 commit 格式。合併後刪分支。

### 一次一個 PR

前一個 PR 合併（或關閉）後才開下一個分支。兩個 PR 並行時，後一個常建立在沒審過的程式上，前一個一改就要重做，
也會改到同一批檔案互相衝突；一次審一件事，diff 才小得好讀。

等合併時可以討論下一件事，但不開分支、不動檔案。正式環境出問題等不及時，由使用者決定要不要插隊
（AI agent 照 `hotfix`）。agent 這一側由 hook 確認：有自己開著的 PR 時，開分支、worktree、PR 要使用者同意，
Dependabot 的 PR 不算（[說明](extending/agent-hooks.md#一次一個-pr)）。

### GitHub 設定

GitHub 端設定一次，流程才不靠自覺：

- [ ] Settings → General → Pull Requests：只勾 **Allow squash merging**，預設訊息選
  **Pull request title and commit details**，勾 **Automatically delete head branches**
- [ ] Settings → Rules：替 `main` 建 ruleset（General 的設定任何管理員都能悄悄改回，ruleset 才是真正擋住的一層）：
  - **Restrict deletions**、**Block force pushes**：預設勾起，保持
  - **Require linear history**：有 bypass 權限的人直接 push 也不會出現 merge commit
  - **Require a pull request before merging**，**Allowed merge methods** 只留 **Squash**
  - **Require status checks to pass**：只加入 `ci-gate`（`ci.yml` 的總閘）與 `pr`（`pr.yml`），勾
    **Require branches to be up to date before merging**。`ci-gate` 等 `ci.yml` 的全部 job，新增或改名 job
    不必回來改；不要另外加個別的 job，docs 模式下它們會被跳過
- [ ] Settings → Advanced Security（或 Code security）：三項都開，少一項安全更新就不會來（見〈相依升級〉）：
  - **Dependency graph**：從 lock 檔解析相依清單，後兩項都靠它
  - **Dependabot alerts**：比對漏洞資料庫，在 Security 分頁發警示
  - **Dependabot security updates**：針對警示自動開升級 PR

## 提交與 CI

- PR 標題與 commit：[Conventional Commits](https://www.conventionalcommits.org/zh-hant/v1.0.0/)，`<type>: <祈使句>`
  （`feat: add product list page`）。PR 標題是硬規定（squash 後留在 `main`），分支上的 commit 建議照寫。
  標題與描述三段由 `pr.yml` 檢查，在 GitHub 上改標題或描述也會重跑。
- CI 通過，實質改動在 [`CHANGELOG.md`](../CHANGELOG.md) 的 `## [Unreleased]` 留一筆。
- commit 訊息不能有 GitHub 的 CI 略過標記（`[skip ci]` 這類與 `skip-checks: true`，`.githooks/commit-msg` 擋）：
  squash 會把每個 commit 的訊息併進 `main`，帶著它 `main` 就不跑 CI，部署也找不到 CI 結果。
  要略過檢查就寫成 workflow 的條件。

CI（`.github/workflows/ci.yml`）每個檢查項目各自一個 job、平行跑，跑的就是本機的 `make check <項目>`：
`lint`、`contract`、`migrate`、`types`、`web-test`、`build`、`api-test`、`api-integration`（`make check integration`）、
`e2e`（另外確認 web image 沒有真的 Server Action 金鑰）。最後由 `ci-gate` 等全部 job 跑完再判定，
ruleset 只要求它（`.github/scripts/ci-gate.sh`）。**完整的檢查只在 CI 跑**：本機在寫測試時只跑單項，
push 之後等 CI 的結果，有錯就修正再 push（新的 commit 會取消還在跑的舊 run）。
部署由 `deploy.yml` 在 Publish release 時執行（[說明](operations.md#自動部署)）。

**docs 模式**：PR 改的檔案全部是 Markdown 時，只跑 `api-test` 與 `web-test`（文件的連結與格式檢查在裡面），
其餘 job 跳過，`ci-gate` 照樣通過。有任何一個非 `.md` 檔，或不是 PR（push `main`、部署、手動執行）就跑全部
（`.github/scripts/ci-mode.sh`）。

為了省時間，CI 有三處與本機不同，檢查內容不變：

- `e2e` 用 Actions 快取先建好 api、web 的 image，以 `API_IMAGE`、`WEB_IMAGE` 交給 `make check e2e`；
  建法（target、快取 scope）與 `deploy.yml` 相同。
- 前端的 job 快取 `apps/web/node_modules`，`.nvmrc`、`package.json`、`package-lock.json` 都沒變就跳過 `npm ci`。
- `lint` 下載固定版本的 shellcheck（`scripts/lib/shellcheck.sh`，核對 sha256），不用 runner 內建的：
  版本不同時同一份腳本會一邊綠一邊紅。本機版本不同時 `make check lint` 提醒，CI 上不同則失敗。

### AI 協作的共同作者

AI 參與的 commit 在訊息最後加 `Co-authored-by`，history 才看得出是哪家、哪個模型做的：

```text
feat: add product list page

列表改用游標分頁, 資料量成長後 offset 會越來越慢。

Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>
```

- **名稱寫到模型與版本**（`Claude Opus 5.5`）：同一家的模型能力差很多，追問題時要分得出來。
- **email 用工具官方的值**，沒有時用 `noreply@<廠商網域>`（GitHub 上只顯示文字、不連頭像，紀錄作用一樣）。
- trailer 放最後、前面空一行，一位一行；多個 AI 參與就各寫一行。
- **`.githooks/commit-msg` 檢查 agent 的 commit**：`AI_AGENT` 有值時（Claude Code 自己會設，Codex 由
  `.codex/config.toml` 補上）沒有 trailer 或名稱沒寫版本就擋下；人自己 commit 不檢查。要 `make init dev` 設好
  `core.hooksPath` 才生效。squash 時 GitHub 會把 trailer 帶進 `main`，合併時不要刪。

查共同作者：

```bash
git log --format='%h %s%n  %(trailers:key=Co-authored-by,valueonly,separator=%x2C )'
```

### 相依升級

上線後**不追最新版，只在有漏洞時升**（`.github/dependabot.yml`）：

- **套件與 GitHub Actions**：Dependabot 只開安全更新（要開 Settings 的三項，見〈GitHub 設定〉）。
- **Docker image**：漏洞資料庫不涵蓋 image，每月一次 PR，只送 patch（nginx 1.31.7 → 1.31.8）。
- **整批升級**：發版前盤點落後多少再決定範圍：開分支、升級、push 讓 CI 跑完、實際建 image 跑起來，再開 PR。
  api Dockerfile 用 `COPY --from` 帶的 uv、CI 下載的 shellcheck（`scripts/lib/shellcheck.sh`）不在 Dependabot 範圍，
  要用 `docker scout` 之類掃 image 才看得到。Dependency graph 的「Check for updates」在版本更新關掉後不會開 PR，不能取代盤點。

遇到 peer 相容性阻擋就**停在最新的相容版**，不要 `--force`／`--legacy-peer-deps`，在設定檔寫下為什麼停與移除條件。
目前 ESLint 停在 9.x（`eslint.config.mjs`）、TypeScript 停在 5.x（`package.json` 的 `//devDependencies`），
`dependabot.yml` 也 ignore 了 major，移除條件成立時兩邊一起拿掉。
