# 開發指南

本機環境、指令、測試策略、開發流程與程式碼風格。擴充功能見 [`extending/`](extending/README.md)，
部署與維運見 [`operations.md`](operations.md)。

## 開發環境

需要 Docker Desktop、`make`、`openssl`、`uv` 與 Node.js（版本見 [`apps/web/.nvmrc`](../apps/web/.nvmrc)；
升 Node 時 `apps/web/Dockerfile` 的 `ARG NODE_VERSION` 要手動跟上）。

```bash
make init dev   # 產生 .env（MODE=development，金鑰自動產生）、安裝相依、git init
make start      # 啟動 postgres → migrate → api → web → nginx（首次建置約 2–5 分鐘）
```

環境起來之後用 `make db superuser` 建立第一個帳號（網頁上沒有註冊入口），再打開
`http://localhost:{SYSTEM_PORT}`（預設 3000）登入。`migrate` 停在 `Exited (0)`、`nginx` 沒有 `(healthy)`
都是正常的。

### 用手機測試

```bash
make start lan  # 同 make start，但對區網開放，結束時印出手機要開的網址
```

平常 nginx 只綁 `127.0.0.1`，手機連不進來。`make start lan` 只在這次啟動改綁 `0.0.0.0`，
下次一般的 `make start` 就關回去，所以**用完跑一次 `make start`**；`.env` 裡沒有對應的設定，刻意不讓它常駐。
開著的時候同一個網路上的人都連得到，在公共 Wi-Fi 上不要用。`MODE=production` 時會被拒絕。

只能用 `http`：瀏覽器只對 `localhost` 放寬安全來源的限制，相機、定位、Service Worker 這類需要 HTTPS 的功能
在 `http://<區網 IP>` 上不能用，要測的話改用會給 https 網址的 tunnel（cloudflared、Tailscale Funnel）。

### 環境變數的同步點

新增環境變數要改這幾處：

| 位置 | 作用 | 漏了的話 |
|---|---|---|
| `.env.example` | 清單，也是 `make init` 產生 `.env` 的範本 | compose 用了 `${X:?}` 卻不在這裡：`make check lint` 擋 |
| `infra/docker/docker-compose.yml` | 注入容器 | **不會報錯**，症狀是「設了卻一直用預設值」 |
| `apps/api/app/config.py`／`apps/web/shared/runtime/config.ts` | 讀取端（哪一邊用就改哪一邊） | 同上 |
| `scripts/init.sh` | **只有**要詢問使用者或自動產生祕密的才改，有固定預設值的直接寫在範本 | 範本裡的空值原樣進 `.env` |

### 起不來的時候

| 症狀 | 怎麼辦 |
|---|---|
| `port is already allocated` | 改 `.env` 的 `SYSTEM_PORT`，`make services down && make start` |
| api 一直重啟、`relation "users" does not exist` | migration 失敗了，`make services logs migrate` 看原因 |
| 容器裡 `ModuleNotFoundError` | 改了相依但 image 沒重建，重建後再 `make start` |
| api 一直重啟、`password authentication failed` 或 `role "app" does not exist` | 資料庫的帳號密碼只在第一次建立 volume 時寫入：改過 `.env` 的 `POSTGRES_PASSWORD`，或 volume 是舊版（帳號不是 `app`）建的。開發機可以清掉重建（**資料會消失**）：`make services down`，`docker volume rm <專案>_development_postgres_data`，再 `make start` 與 `make db superuser` |
| `make init dev` 抱怨 Node 版本 | `nvm use` |
| `make init dev` 說專案名稱已有 docker 服務在使用 | 換一個名稱；確定是不要的舊專案，就用 `docker rm`／`docker volume rm` 清掉列出的資源 |

## 指令

一個主題一個指令，第二個字選動作。完整說明看 `make help`：

```bash
make init dev|prod                           # 產生 .env 並寫入 MODE；prod 只產生 .env（部署主機用）
make start [lan]                             # 依 .env 的 MODE 啟動；lan = 開放區網讓手機連（僅 development）
make services [volumes|logs [服務]|restart|down]   # 不帶參數 = 版本與 MODE、服務狀態、volume；restart = 原地重啟
make backup                                  # 資料庫與上傳檔案一起備份，期間對外服務暫停
make db   psql|restore [檔案]|reset|migrate|migration "說明"|superuser
make uploads restore [檔案]
make check [lint|contract|migrate|types|test|build|integration|e2e]   # 不帶參數 = 前六項，送出前跑
make gen-types                               # 改過後端 schema／權限／語系後必跑
```

**`MODE` 決定這台主機是哪種環境。** `make init dev|prod` 寫進 `.env`，只在第一次產生時決定；
要換就刪掉 `.env` 重跑，或手動改那一行。`make start` 依它疊 dev 或 prod 的 overlay，缺少或不是
`production`／`development` 時，碰容器的指令一律停下來。開發機要驗證 production build，就暫時改成
`MODE=production`（volume 名稱帶著 `MODE`，開發資料不會被動到），驗完改回來。
`MODE=production` 時擋下的指令見 [`operations.md`](operations.md#生產部署)。

實作在 `scripts/<指令>.sh`，可以直接執行（`./scripts/db.sh psql`）。新增子指令＝改那支腳本的
`case`，並在檔頭補一行 `#   make …`（`make help` 讀的就是它）；新增指令＝加一支腳本並把名稱
加進 Makefile 的 `TARGETS`。部署與腳本自己用的指令寫成 `#   [內部] make …`，不列在 help，
只寫在 [`operations.md`](operations.md#內部指令)。

## 測試

```bash
make check test                             # 前後端全部（帶覆蓋率）
make check integration                      # 起拋棄式 PostgreSQL 跑 integration + alembic check
make check e2e                              # 起拋棄式的正式環境，用 Playwright 從瀏覽器跑過整條路
cd apps/api && uv run pytest tests/ -k xxx  # 只跑後端某些測試
cd apps/web && npm run test:watch           # 前端 watch 模式
```

### 測試放哪裡

**一律放該 app 的 `tests/`，與原始碼同構**：`tests/modules/users/` 對 `modules/users/`、
`tests/shared/auth/test_passwords.py` 對 `shared/auth/passwords.py`、
`tests/shared/access/permissions.test.ts` 對 `shared/access/permissions.ts`。
放在 `tests/` 以外的測試不會執行，也不會報錯；`tests/` 裡對不上原始碼目錄的子目錄由架構測試擋。

- **依賴專案啟用清單的測試**（註冊表、權限覆蓋、每張已註冊資料表的慣例）放後端 `tests/app/`、
  前端 `tests/` 根目錄或 `tests/config/`。
- **一個模組的測試只放在它自己的目錄**，不要在 `tests/modules/` 根目錄寫同時測好幾個模組的檔案：
  刪模組時是整包刪 `tests/modules/<name>/`，跨模組的測試會留下來並因為引用不到而失敗。
- **`tests/shared/` 不綁專案目前有的端點與權限**：測執行期行為時用與專案無關的路徑
  （例：`tests/shared/api/request.server.test.ts`），刪掉模組時這批測試才不會跟著壞。
- **從公開函式進入**，不直接測 `_` 開頭的私有函式：規則有兩個入口時，只測輔助函式證明不了
  兩邊都有套用（例：`tests/modules/users/test_service.py` 的停用規則）。

| 要 test-first | 不寫執行期測試 |
|---|---|
| `shared/**`（前後端） | 前端 `modules/*/actions.ts`（薄包裝，型別由 OpenAPI 擋） |
| 前端 `capabilities.ts`、`validation.ts`、`proxy.ts` | 前端 `modules/*/ui/*.tsx`（畫面組裝） |
| 後端 service、router、權限 | route adapter（由 `route-adapters.test.ts` 靜態守住） |

畫面裡真的有分支時，**抽進 `capabilities.ts` 再測**（例：`modules/users/capabilities.ts`）。
不要為了覆蓋率數字補測試。

**不寫的測試**（寫了只是維護成本，帶到新專案就是技術債）：

- 只驗框架或語言本身的行為：React 會渲染 children、`onClick` 會被呼叫、set 不會重複。
- 型別系統或啟動檢查已經保證的：必填欄位有沒有寫、回傳值是不是某個 enum、enum 與權限
  metadata 是否一一對應（`app.registry` 載入時就驗了）。
- 把常數再寫一次的：`assert UNLOGGED_PATHS == {"/health"}` 這類，改值就得同步改測試，
  卻擋不住任何錯；改測它造成的行為。
- 寫死專案目前內容的：「管理區是 `/admin/users`、`/admin/roles`」、「身分來源是 users 模組」。新增或移除
  模組時它會紅，但什麼都沒壞。從啟用清單推導（例：`tests/config/routes.test.ts`）。
- 同一個行為在另一層已經測過的：薄包裝（只是把 A 接到 B）不再各測一次。

### E2E（`e2e/`）

`make check e2e` 另起一套 compose 專案（`<專案>-e2e`，port 預設 3900，可用 `E2E_PORT` 換），
用**正式環境的 image 與 nginx 模板**，以 CLI 建一個隨機密碼的超管，跑完 Playwright 後連 volume 一起刪掉，
開發中的那套不受影響。第一次跑會下載 Chromium（幾百 MB），之後沿用。CI 是獨立的 `e2e` job，
與其他 job 平行跑；失敗時到該次執行的 Artifacts 下載 `playwright-report`，trace 用
`npx playwright show-trace <zip>` 打開。

**只放跨層的 smoke 測試**：proxy 導向、cookie 屬性、Server Action、權限導向、撤銷這類只有整套跑起來才看得到的行為。
畫面分支仍然抽進 `capabilities.ts` 用 vitest 測，不要寫成 E2E（慢，而且畫面一改就要跟著改）。

- 測試名稱與前端一樣用讀得通的中文句子，斷言也用中文文案（`locale: "zh-TW"`）。
- 選元素用 `getByRole`／`getByLabel`，不要用 class 或 DOM 結構。
- 等待用 `expect(...).toBeVisible()`／`toHaveURL()` 這類會自動重試的斷言，**不要寫固定的 sleep**；
  也刻意不開 retries，偶發失敗要修等待條件。
- API 沒有對外開放，測試資料只能從畫面建立，所以同一個檔案裡依序執行（`mode: "serial"`）。

### 寫法

- **後端單元測試**：`tests/modules/conftest.py` 的 `client` fixture 直接打 app，service 與資料表
  方法用 monkeypatch 換掉，不需要資料庫（例：`tests/modules/users/test_routes.py`）。
- **後端 integration 測試**：標 `@pytest.mark.integration`，用 `tests/integration.py` 的
  `require_postgres` 拿資料庫。本機沒資料庫時會 skip（`make check test` 結尾會提醒），
  CI 上 skip 視為失敗。
- **前端**：Vitest + Testing Library。`.server.ts` 一樣能測：`server-only` 在測試裡換成空模組，
  Next 的請求上下文（`cookies`、`headers`、`redirect`）用 `vi.mock` 換掉
  （例：`tests/shared/api/request.server.test.ts`）。

### 架構本身也有測試

| 守什麼 | 在哪 |
|---|---|
| 依賴方向、跨模組只走 public entry | 後端 import-linter（`pyproject.toml`）、前端 dependency-cruiser（`.dependency-cruiser.cjs`） |
| 模組內部用相對路徑、manifest 不用瀏覽器 API | ESLint（`eslint.config.mjs`） |
| client 不可引用 `.server` 檔 | Next.js build（每個 `.server` 檔都 `import "server-only"`） |
| 模組的檔案放置、不准水平分層、測試目錄與原始碼同構 | `apps/web/tests/architecture.test.ts`、`apps/api/tests/test_architecture.py` |
| 每個原始碼目錄都在依賴邊界的掃描範圍裡（`check:architecture`、`root_packages`） | 同上 |
| route adapter 是薄的、Next 特有 export 有接上 | `apps/web/tests/app/route-adapters.test.ts` |
| 路由清單與 `app/` 的頁面兩邊對得上、頁面放在對的區 | `apps/web/tests/config/routes.test.ts` |
| Next 有認到 `proxy.ts` | `make check build`（輸出要有 `ƒ Proxy (Middleware)`） |
| 寫 session cookie 的 action 回傳前經過 `withoutAccessToken` | `apps/web/tests/token-cookie-writers.test.ts` |
| 不用 `NEXT_PUBLIC_*` | `apps/web/tests/runtime-env.test.ts` |
| 後端錯誤不用裸的 `HTTPException` | ruff `TID251`（`pyproject.toml`） |
| 後端 service 回傳 pydantic model（不是 dict）並寫回傳型別 | `apps/api/tests/test_service_returns.py`、mypy `disallow_untyped_defs` |
| compose 只由 `scripts/lib/compose.sh` 呼叫 | `apps/api/tests/test_compose_usage.py` |
| 沒有未使用的匯出 | knip（`npm run check:deadcode`） |
| model 改了有寫 migration | `make check integration` |
| nginx 每個 location 都覆寫用戶端 IP、兩份模板都帶安全標頭 | `apps/api/tests/test_nginx_templates.py` |
| 容器 nginx 只信任私有網段、port 只綁 `127.0.0.1`、主機範例覆寫轉送標頭 | `apps/api/tests/test_nginx_trusted_proxy.py` |
| nginx 與 Next 的上傳上限一致 | `apps/web/tests/next.config.test.ts` |
| nginx 的模板變了 `make start` 會重建 nginx | `apps/api/tests/test_nginx_config_recreate.py` |
| `scripts/` 的 shell 寫法 | shellcheck（`make check lint`） |
| compose 展得開、用到的變數 `.env.example` 都有 | `docker compose config`（`make check lint`） |
| 契約與前端型別是最新的 | `make check contract`（只比對、不改檔） |
| 已發版的 migration 沒有被修改或刪除 | `make check migrate`（`apps/api/tests/test_migration_checks.py`） |
| 部署不會讓資料庫往回、整組都檢查過才部署 | `deploy.yml` 的 `migration-check`（`apps/api/tests/test_migration_checks.py`、`test_deploy_targets.py`） |
| GHCR 只清沒有標籤的版本、清完確認所有標籤都完整、刪除權限只給清理 | `deploy.yml` 的 `cleanup-ghcr`（`apps/api/tests/test_ghcr_cleanup.py`） |
| `make start` 先單獨跑 migrate，失敗不切換服務 | `apps/api/tests/test_stack_scripts.py` |
| api 開機時不寫資料，初始資料由 migrate 寫入 | `apps/api/tests/shared/test_platform.py`、`apps/api/tests/scripts/test_db.py` |
| `shared/` 用到的 CSS 變數都定義在 shared 裡 | `apps/web/tests/shared/ui/tokens.test.ts` |
| `APP_VERSION` 與 CHANGELOG 的版號一致 | `apps/api/tests/test_version.py` |
| 文件的相對連結與錨點有效、原始碼寫的 `docs/….md` 路徑存在、`extending/`、`features/` 與 ADR 都列在索引、`features/` 的開頭與結尾段落、ADR 的取代關係兩邊一致 | `apps/api/tests/test_docs.py`、`test_doc_features.py`、`test_doc_decisions.py`、`test_doc_decision_supersession.py` |

規則本身見 [`architecture.md`](architecture.md#強制依賴規則)。

### 改程式不改測試

理解需求後先把測試寫好，再開始實作。測試是需求的定義，實作期間改測試等於改需求，所以由人決定。
**單元測試、integration 與 `e2e/` 的 E2E 測試一律適用**，測試用的輔助檔與資料（例如 `e2e/tests/support.ts`、
測試沙盒要複製的檔案清單）也算測試檔：

1. 測試變紅時預設它是對的，先改實作讓它變綠。
2. 真的覺得測試要改（介面改名、斷言本來就寫錯、漏了情境要補）時，**先停下來說明**那個測試驗證的條件、
   沒過的原因，以及為什麼是測試而不是實作要改。
3. 得到同意後才動測試檔，並在 PR 描述寫明**原本那個斷言為什麼是錯的**。

紅燈階段用單項指令跑（`uv run pytest tests/ -k xxx`、`npm run test -- -t "名稱"`），
`make check` 要等實作完成、全部轉綠才會過。

### 驗收條件與測試名稱

PR 描述「驗證」段的每條驗收條件後面接一個測試名稱與結果。**寫不出測試名稱的那一條，就是動手前要先問清楚的地方。**

- 前端與 E2E：讀得通的中文句子（`未登入導向 /login`、`登出後其他已登入的裝置也會被登出`）
- 後端：`test_<動作>_<條件>_<結果>`（`test_get_users_without_permission_returns_403`）

驗收條件只寫在 PR，不另寫一份文件或 spec：PR 是動手前討論方向的地方，合併後留下來的是測試名稱，
它會跟著程式一起被執行，文件則會在下一次改動時悄悄過時。

覆蓋率門檻（`pyproject.toml` 的 `fail_under`、`vitest.config.ts` 的 `thresholds`）是**防退步的地板，
不是目標**。

## 開發流程

每個改動都走同一條路，`main` 只透過 PR 前進：

```text
Feature Branch → Draft PR → Incremental Commits → Code Review → Squash Merge
```

1. **Feature Branch**：從最新的 `main` 開分支，命名 `<type>/<kebab-case>`（`feat/product-list`）。
   不直接 push `main`。一個分支只做一件事，做到一半發現別的問題就另開分支，不要順手塞進來。
2. **Draft PR**：分支第一次 push 就開 Draft PR（`gh pr create --draft`），先照模板寫「摘要」與
   [驗收條件](#驗收條件與測試名稱)。動手前就把方向攤開，方向錯了在寫程式之前就會被看到。
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
    加進去，並勾 **Require branches to be up to date before merging**，CI 是跟最新的 `main` 一起跑過的。
    CI 多了 job 時要回來這裡加：沒列進去的 job 紅了，PR 照樣能合併
- [ ] Settings → Advanced Security（有的帳號叫 Code security）：三項都要打開，少一項安全更新就不會來
  （套件只收安全更新，見〈相依升級〉）：
  - **Dependency graph**：從 lock 檔與 manifest 解析出相依清單，後兩項都靠它
  - **Dependabot alerts**：拿相依清單比對漏洞資料庫，有漏洞時在 Security 分頁發警示
  - **Dependabot security updates**：針對警示自動開升級到修補版的 PR

## 提交與 CI

- PR 標題與 commit：[Conventional Commits](https://www.conventionalcommits.org/zh-hant/v1.0.0/)，
  `<type>: <祈使句>`（`feat: add product list page`）。PR 標題是硬規定（squash 後留在 `main`），
  分支上的 commit 建議照寫。
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
- Git 與 GitHub 都不強制這行，漏了不會報錯，所以靠每個 commit 自己帶。squash 時 GitHub 會把分支上的
  trailer 帶進 `main` 的內文，合併時不要把它們刪掉。

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

## 程式碼風格

由 lint 擋的上限（防退步的地板，不是重構目標）：

| 規則 | 前端 `.ts` | 前端 `.tsx` | 後端 |
|---|---|---|---|
| 單行長度 | 100 字元 | 100 字元 | 100 顯示寬度（中文算 2） |
| 巢狀深度 | 4 | 4 | — |
| 循環複雜度 | 10 | 15 | 10 |
| 函式長度 | 60 行 | 100 行 | 40 敘述 |

靠 review 的：

- **一個函式一件事**：需要用「而且」才描述得完，就該拆。
- **早退出**：前置條件不成立就 `return`。
- **命名見義**：讀不出意圖的長布林運算式，給它一個名字。
- **不留死碼**：註解掉的程式碼、「之後可能會用到」的分支一律刪掉。

### 註解與文件

註解寫**為什麼**，不寫做了什麼 —— 尤其是「為什麼不用另一種看起來更自然的做法」。一個取捨一段，
講完就停；演進過程寫進 commit message。註解與文件用繁體中文，技術名詞保持原文。
程式碼裡的註解與 docstring 用**半形標點**（`, : ; ( ) ? /`，逗號、冒號後面空一格）：全形的
`，：（）` 會被編輯器標成「可能與 ASCII 字元混淆」。Markdown 文件與使用者看得到的字串（i18n、
終端訊息、測試名稱）維持全形。
文件**一個主題一個 owner**，其他地方只放連結；範例指向 repo 內的真實檔案。
