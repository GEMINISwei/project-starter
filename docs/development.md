# 開發指南

本機環境、指令、測試策略、開發流程與程式碼風格。擴充功能見 [`extending.md`](extending.md)，
部署與維運見 [`operations.md`](operations.md)。

## 開發環境

需要 Docker Desktop、`make`、`openssl`、`uv` 與 Node.js（版本見 [`apps/web/.nvmrc`](../apps/web/.nvmrc)；
升 Node 時 `apps/web/Dockerfile` 的 `ARG NODE_VERSION` 要手動跟上）。

```bash
make init    # 產生 .env（金鑰自動產生）、安裝相依、git init
make dev     # 啟動 postgres → migrate → api → web → nginx（首次建置約 2–5 分鐘）
```

打開 `http://localhost:{SYSTEM_PORT}`（預設 3000），第一次會落在 `/signup`，填 `make init`
印出的 `REGISTER_KEY` 建立第一個帳號。`migrate` 停在 `Exited (0)`、`nginx` 沒有 `(healthy)`
都是正常的。

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
| `port is already allocated` | 改 `.env` 的 `SYSTEM_PORT`，`make dev down && make dev` |
| api 一直重啟、`relation "users" does not exist` | migration 失敗了，`make dev logs migrate` 看原因 |
| 容器裡 `ModuleNotFoundError` | 改了相依但 image 沒重建，重建後再 `make dev` |
| `make init` 抱怨 Node 版本 | `nvm use` |
| `make init` 說專案名稱已有 docker 服務在使用 | 換一個名稱；確定是不要的舊專案，就用 `docker rm`／`docker volume rm` 清掉列出的資源 |

## 指令

一個主題一個指令，第二個字選動作。完整說明看 `make help`：

```bash
make init [env]                              # env = 只產生 .env（部署主機用）
make dev  [up|down|logs [服務]|ps]           # prod 同一組子指令（prod 的 up 會重新建置 image）
make db   psql|backup|restore [檔案]|reset|migrate|migration "說明"|superuser
make check [lint|types|test|build|portable|integration|contract]   # 不帶參數 = 前五項，送出前跑
make gen-types                               # 改過後端 schema／權限／語系後必跑
make version                                 # 目前的版本（APP_VERSION）
```

實作在 `scripts/<指令>.sh`，可以直接執行（`./scripts/db.sh backup`）。新增子指令＝改那支腳本的
`case`，並在檔頭補一行 `#   make …`（`make help` 讀的就是它）；新增指令＝加一支腳本並把名稱
加進 Makefile 的 `TARGETS`。

## 測試

```bash
make check test                             # 前後端全部（帶覆蓋率）
make check integration                      # 起拋棄式 PostgreSQL 跑 integration + alembic check
cd apps/api && uv run pytest tests/ -k xxx  # 只跑後端某些測試
cd apps/web && npm run test:watch           # 前端 watch 模式
```

### 測試放哪裡

**一律放該 app 的 `tests/`，與原始碼同構**：`tests/modules/users/` 對 `modules/users/`、
`tests/shared/auth/test_passwords.py` 對 `shared/auth/passwords.py`、
`tests/shared/access/permissions.test.ts` 對 `shared/access/permissions.ts`。
放在 `tests/` 以外的測試不會執行，也不會報錯；`tests/` 裡對不上原始碼目錄的子目錄由架構測試擋。

- **依賴專案啟用清單的測試**（註冊表、權限覆蓋、每張已註冊資料表的慣例）放後端 `tests/app/`、
  前端 `tests/` 根目錄或 `tests/config/`，不放 `tests/shared/`。
- **一個模組的測試只放在它自己的目錄**，不要在 `tests/modules/` 根目錄寫同時測好幾個模組的檔案：
  刪模組時是整包刪 `tests/modules/<name>/`，跨模組的測試會留下來並因為引用不到而失敗。
- **`tests/shared/` 不可依賴專案**（端點、權限、業務 entity）：它要跟著 shared 一起移植。
  測執行期行為時用與專案無關的路徑（例：`tests/shared/api/request.server.test.ts`），
  `make check portable` 會擋。
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
| route adapter 是薄的、Next 特有 export 有接上 | `apps/web/tests/app/route-adapters.test.ts` |
| 沒有未使用的匯出 | knip（`npm run check:deadcode`） |
| model 改了有寫 migration | `make check integration` |
| nginx 每個 location 都覆寫用戶端 IP、兩份模板都帶安全標頭 | `apps/api/tests/test_nginx_templates.py` |
| `scripts/` 的 shell 寫法 | shellcheck（`make check lint`） |
| compose 展得開、用到的變數 `.env.example` 都有 | `docker compose config`（`make check lint`） |
| 契約與前端型別是最新的 | `make check contract`（CI） |
| `shared/` 整包複製到空專案還能用 | `make check portable`（[說明](architecture.md#shared-的可移植性)） |
| 後端 `tests/shared/` 不碰 `app`／`modules` | `apps/api/tests/test_architecture.py` |
| `shared/` 用到的 CSS 變數都定義在 shared 裡 | `apps/web/tests/shared/ui/tokens.test.ts` |

規則本身見 [`architecture.md`](architecture.md#強制依賴規則)。

### 改程式不改測試

測試變紅時預設它是對的。真的要改（介面改名、斷言本來就寫錯）時，在 PR 描述寫明
**原本那個斷言為什麼是錯的**。

### 驗收條件與測試名稱

PR 描述的每條驗收條件後面接一個測試名稱。**寫不出測試名稱的那一條，就是動手前要先問清楚的地方。**

- 前端：讀得通的中文句子（`未登入導向 /login`）
- 後端：`test_<動作>_<條件>_<結果>`（`test_get_users_without_permission_returns_403`）

覆蓋率門檻（`pyproject.toml` 的 `fail_under`、`vitest.config.ts` 的 `thresholds`）是**防退步的地板，
不是目標**。

## 開發流程

每個改動都走同一條路，`main` 只透過 PR 前進：

```text
Feature Branch → Draft PR → Incremental Commits → Code Review → Squash Merge
```

1. **Feature Branch**：從最新的 `main` 開分支，命名 `<type>/<kebab-case>`（`feat/product-list`）。
   不直接 push `main`。一個分支只做一件事，做到一半發現別的問題就另開分支，不要順手塞進來。
2. **Draft PR**：分支第一次 push 就開 Draft PR（`gh pr create --draft`），先照模板寫「這個 PR
   做什麼」與[驗收條件](#驗收條件與測試名稱)。動手前就把方向攤開，方向錯了在寫程式之前就會被看到。
3. **Incremental Commits**：小步提交、常常 push，每個 commit 是一個說得清楚的步驟
   （例：先補測試、再實作、再整理）。這些 commit 的訊息會併進 squash 後的內文，所以寫成
   「做了什麼、為什麼」，不要一路 `wip`、`fix`。
4. **Code Review**：`make check` 綠、模板的「送出前」勾完、整份 diff 自己讀過一次，才按
   **Ready for review**。回應 review 用新的 commit，不要 force push 改寫已經被看過的歷史，
   reviewer 才看得出這一輪改了什麼。CI 綠、意見都處理完才合併。
5. **Squash Merge**：一律 **Squash and merge**，`main` 上一個 PR 一個 commit。squash 後的標題就是
   `main` 的 commit 標題，所以 **PR 標題**要符合下面的 commit 格式。合併後刪除分支。

GitHub 端要設定一次，流程才不是靠自覺：

- [ ] Settings → General → Pull Requests：只勾 **Allow squash merging**，預設訊息選
  **Pull request title and commit details**，並勾 **Automatically delete head branches**
- [ ] Settings → Rules：替 `main` 建 ruleset，開 **Require a pull request before merging**，
  並把 CI 的三個 job（`check`、`integration`、`images`）設成 **required status check**

## 提交與 CI

- PR 標題與 commit：[Conventional Commits](https://www.conventionalcommits.org/zh-hant/v1.0.0/)，
  `<type>: <祈使句>`（`feat: add product list page`）。PR 標題是硬規定（squash 後留在 `main`），
  分支上的 commit 建議照寫。
- 送出前通過 `make check`，實質改動在 [`CHANGELOG.md`](../CHANGELOG.md) 的 `## [Unreleased]` 留一筆。

CI（`.github/workflows/ci.yml`）跑的就是本機指令：`check`（`make check` 與
`make check contract`）、`integration`（`make check integration`）、`images`（兩份 production image
建得起來，且 web image 裡沒有真的 Server Action 金鑰）。**本機綠，CI 就綠。** 部署另由
`deploy.yml` 在 Publish release 時執行，見 [`operations.md`](operations.md#自動部署)。

### 相依升級

升版 PR 由 Dependabot 每週開（`.github/dependabot.yml`）。
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
