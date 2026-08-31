# 開發指南

本機開發環境、常用指令、提交規範、測試，以及這個 repo 寫文件與註解的慣例。
擴充功能的作法見 [`extending.md`](extending.md)，部署與維運見 [`operations.md`](operations.md)，
CI 有哪些 job 與 GitHub 那一側的設定見 [`ci-cd.md`](ci-cd.md)。

## 1. 開發環境設置

### 前置需求

- Docker Desktop
- `make`、`openssl`
- `uv` 與 Node.js/npm（用於在主機執行檢查與測試）。Node 的 major 線在
  [`../apps/web/.nvmrc`](../apps/web/.nvmrc)（nvm 與 CI 的 `setup-node` 讀它），
  **下限**在 `apps/web/package.json` 的 `engines`；本機可執行
  `nvm use "$(cat apps/web/.nvmrc)"`，`make setup` 會拿主機的 Node 去比對這兩條線。
  **但 `apps/web/Dockerfile` 讀不到 `.nvmrc`**，它的 `ARG NODE_VERSION` 是要手動跟上的
  第三處 —— **沒有任何東西在比對它與 `.nvmrc`**（`setup.sh` 管的是主機那一側，
  容器裡用哪個版本它看不到）
- `shellcheck`（只有 `make check-shell` 需要，macOS：`brew install shellcheck`）

### 產生設定檔

```bash
make init
```

互動式建立 `.env`，完成後初始化 Git，並把 `REGISTER_KEY` 印在終端機上
（不必再開 `.env` 查看）。已存在的 `.env` 或 Git 都會跳過。

**它不會問任何遠端網址，也不需要網路** —— 只在本機試跑的專案不必綁儲存庫。

正常開案不會走到這裡：用 "Use this template" 開出 repo 再 `git clone`，`origin` 已經
綁好了，`make init` 也會看到 `.git` 而跳過初始化。只有「下載 ZIP」或「`rm -rf .git`
重開歷史」才會需要自己綁：

```bash
git remote add origin <你的 repo 網址>
git push -u origin main
```

需要輸入的欄位：

| 欄位 | 預設值 | 規則 |
|---|---|---|
| 專案名稱 | `my-app` | 小寫英文字母或數字開頭，只能含 `a-z`、`0-9`、`-`、`_` |
| 系統名稱 | `My App` | 不可含單引號 |
| 系統 Port | `3000` | 1–65535 整數 |
| 資料庫帳號 | `admin` | 只能含 `A-Za-z0-9._~-` |
| 資料庫密碼 | 無，必填 | 只能含 `A-Za-z0-9._~-`。這個限制不是美觀問題：它會被插進 compose 組出來的 `postgresql+asyncpg://user:pass@postgres:5432/db`，`@`／`:`／`/` 會把 URL 切在錯的地方 |

資料庫名稱不另外問，直接用專案名稱。`JWT_SECRET_KEY`、`REGISTER_KEY`、
`NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` 與 VAPID 金鑰全部自動產生，不需手動修改。

**完整的環境變數清單與每個變數的意義，見 [`../.env.example`](../.env.example)** ——
那份檔案是清單的唯一出處，這裡不再抄一份。手抄它來建 `.env` 也不可行：
標成「自動產生」的祕密漏掉之後，服務照常啟動，但簽出的 token 任何人都能偽造。

`TOKEN_VERSION` 與單一使用者撤銷的差別見
[`operations.md`](operations.md#session-撤銷)。

### 環境變數的四個同步點

新增一個環境變數要同時改四個地方：

| 位置 | 做什麼 | 自動檢查 |
|---|---|---|
| `.env.example` | 清單與說明 | ✅ `make check-env` |
| `infra/docker/docker-compose.yml` | 注入容器（`check-env` 連 `.dev.yml`／`.prod.yml` 一起掃） | ✅ `make check-env` |
| `scripts/init.sh` | 產生 `.env` | ✅ `make check-env` |
| `apps/api/app/config.py` | 後端讀取 | ✅ `make check-env` |

`make check-env` 比對前三者的變數集合，比對 `.env.example` 與 `scripts/init.sh` 之間的
字面預設值（compose 的 `${VAR:-…}` 不在比對範圍），確認祕密欄位在 `.env.example` 裡留空，
並雙向比對 `AppEnv` 的欄位與 compose 注入給 `api` 的環境變數 —— 那一處的兩種錯都不會讓
任何指令失敗：欄位沒被注入是「`.env` 設了卻一直用預設值」，注入了沒有對應欄位則是
「設定的人以為自己開了某個功能，pydantic-settings 直接忽略它」。

刻意不比對 `migrate` 服務：它跑的 `scripts/db.py` 直接讀 `os.environ`（只要三個變數），
沒有經過 `AppEnv`。用同一組規則對它，只會要求它帶上根本用不到的 `JWT_SECRET_KEY`。

只給主機端腳本用、不進任何容器的變數（目前是 `IMAGE_REGISTRY` 與 `IMAGE_TAG`）
列在 `scripts/check-env.sh` 的 `HOST_ONLY`，只要出現在 `.env.example` 與 `init.sh` 兩處。
**這一欄短才是常態** —— 長長一串代表 `.env` 開始承擔它不該承擔的東西。

第五個同步點只有一個，而且**沒有檢查器**：走 registry 部署時 `UPLOAD_SIZE_LIMIT`
要與 GitHub 那邊的 repository variable 一致。理由、代價與它的開機自檢見
[`operations.md`](operations.md#registry-模式唯一的-build-期值)。

### 啟動

```bash
make dev
```

首次啟動會建置 Docker image，約需 2–5 分鐘。啟動後：

| 服務 | 位址 |
|---|---|
| 前端 | `http://localhost:{SYSTEM_PORT}`（預設 http://localhost:3000） |
| API（同源轉送） | `http://localhost:{SYSTEM_PORT}/api` |

後端服務本身只開放在 Docker 內部網路的 `api:8000`，不直接暴露到主機。
資料庫沒有網頁 GUI，要看內容用 `make psql`。

**有兩個東西看起來像壞掉、其實正常**，第一次跑 `make dev` 的人幾乎都會問：

- **`migrate` 停在 `Exited (0)` 不是沒跑完。** 它是一次性容器，建完表、跑完未套用的
  migration 就結束，Docker Desktop 會一直把它列在停止狀態。常駐的是 `postgres`、`api`、
  `web`、`nginx` 四個。
- **`nginx` 沒有 `(healthy)` 也是正常的。** 四個常駐服務裡只有它沒定義 healthcheck，
  而沒定義的容器只會顯示 `Up` —— 那不是「不健康」，是「沒有人在探」。

兩者通常都不必看：`api` 起得來本身就是 migration 成功的證據，理由與判讀方式見
[`operations.md`](operations.md#部署成功長什麼樣)。

第一次進站要建立超級管理者，流程與它的一次性設計見
[`operations.md`](operations.md#首次初始化建立第一個超級管理者)。

### 起不來的時候

第一天最常卡住的六個地方。**每一條都是症狀不會指回原因的那種**，
一眼看得出來的（打錯指令、少裝一個套件）就不列了。

| 症狀 | 原因 | 怎麼辦 |
|---|---|---|
| `Cannot connect to the Docker daemon` | Docker Desktop 沒開 | 開它，等鯨魚圖示不再轉 |
| `port is already allocated` | `SYSTEM_PORT` 被別的東西佔了 | `lsof -i :3000` 找出來，或改 `.env` 的 `SYSTEM_PORT` 後 `make down && make dev` |
| 後端一直重啟、log 是 `relation "users" does not exist` | migrate 沒跑成功（資料表還沒建），多半是它自己先失敗了 | `make logs` 看 `migrate` 容器說了什麼；結構真的亂了就 `make reset && make migrate`（**會清空資料**，只在 dev 用） |
| `make setup` 抱怨 Node 版本 | 主機 Node 與 [`apps/web/.nvmrc`](../apps/web/.nvmrc) 不同 | `nvm use`（或裝上那個版本）。注意 `apps/web/Dockerfile` 的 `ARG NODE_VERSION` 是**第三處**版本號，沒有檢查器在守 |
| 任何指令說 `.env` 缺這個缺那個 | 沒跑過 `make init`，或改動加了新變數卻沒補進 `.env` | 跑 `make check-env`，它會指出四個同步點中哪一處對不上 |
| `make dev` 卡在建置很久 | 首次建置沒有 layer 快取 | 正常，2–5 分鐘。第二次起會快很多 |

再往下的線索一律看 log：`make logs` 會依目前的運行模式選服務。

## 2. 常用指令

`make help`（不帶目標時的預設行為）會列出全部指令與說明，指令清單直接來自 `Makefile`
的 `TARGETS`、每一行說明來自對應腳本的標頭註解。**清單不會脫節，但那一行說明會** ——
腳本長出第二件職責時沒人強迫更新它，所以要知道某支檢查器到底守了什麼，以這份文件為準。
以下只列日常會用到的幾類：

<!-- check-docs: commands check- -->

| 類別 | 指令 |
|---|---|
| 初次設定 | `make init`（建立 `.env`）、`make setup`（主機端相依：`uv sync --frozen` + `npm ci`） |
| 環境 | `make dev`、`make prod`、`make deploy`、`make down`、`make logs` |
| 資料庫 | `make psql`、`make migrate`、`make reset`、`make backup`、`make restore` |
| 帳號 | `make create-superuser` |
| 型別契約 | `make gen-types`（**改過後端 schema／權限／WS 事件後必跑**，CI 會擋） |
| 檢查 | `make lint`、`make typecheck`、`make test`、`make build`、`make check`、`make e2e`、`make audit` |
| 原始碼外的檢查 | `make check-acceptance`、`make check-ci`、`make check-compose`、`make check-contracts`、`make check-docs`、`make check-env`、`make check-nginx`、`make check-shell`、`make check-test-edits`、`make check-version` |

`lint`、`typecheck`、`test`、`build`、`check` 直接在主機執行，首次使用前請先跑 `make setup`。
`typecheck` 會先執行 `next typegen` 再跑 `tsc`；Next 產生的 `next-env.d.ts` 不進版控，
避免 `next dev` 與 `next build` 交替時因輸出目錄不同而反覆改寫工作樹。

`make audit` 與 `make check` 分開是刻意的：audit 要連外部 advisory 資料庫，而 `check` 是每次
改完程式都要跑的東西，不該因為離線就失敗。audit 也會因為「今天有人公布新漏洞」而變紅，
那跟你這次改了什麼無關。CI 有獨立的 security job 跑它，相依更新由 `.github/dependabot.yml`
自動開 PR（uv／npm／docker／docker-compose 每週，GitHub Actions 每月）。

那排 `check-*` 也都不在 `make check` 裡，因為 `check` 涵蓋的是**原始碼**，而它們守的是
設定、產出物、文件與 shell 腳本 —— 那類東西壞掉時，lint／typecheck／test／build
全部照樣綠燈。它們各自掛在該掛的地方：`check-contracts` 由 `gen-types` 跑完自動叫一次，
`check-acceptance` 與 `check-test-edits` 要讀 PR 描述，所以跟 CHANGELOG 的守衛一起
收在 CI 的 PR-only job `pr-checks` 裡（各一個 step），其餘全部在 CI 的 `deploy-config` job。
改過 `.env.example`、`scripts/init.sh`、compose 檔、
nginx 模板、任何 `scripts/*.sh` 或任何 `.md` 之後，本機補跑一次對應的那支最快。

`check-nginx` 守兩件事。一是**限流的前提**：後端只讀 `X-Real-IP` 而且無條件信任它，
所以每個帶 `proxy_pass` 的 location 都必須用 `$remote_addr` 覆寫它與 `X-Forwarded-For`。
漏掉一個 location 的症狀是所有人共用同一個限流 key，而且完全靜默 —— 詳見
[`operations.md`](operations.md#用戶端-ip-與限流)。例外列在腳本頂端的 `ALLOW`，
**每條都要附理由**。二是 `nginx -t` 的**語法檢查**（版本跟著 compose 走）：
少了它，打錯一個分號不會被任何 job 發現，而 nginx 是唯一對外的服務 ——
它 crash-loop 等於整個站起不來。沒有可用的 docker 時只跳過語法那一半。

`check:tokens` 是 `check-boundaries.mjs` 的 CSS 對應物，跟著 `npm run lint` 一起跑
（所以在 `make check` 裡）。它守的是 token 分層與 CSS 的死碼，也就是
`check-boundaries.mjs` 看不到的那一半，規則清單與理由見 [`design-system.md`](design-system.md)。

`check-docs` 守的是文件裡的指路：markdown 連結目標、反引號裡的路徑，以及
「大寫開頭的擁有者加一個點」那種識別字（`BaseTable.ensure_seed`、`Permission.ALL`）。
文件漂移都長這樣 —— 文件教一個後端已經不用的慣例，照抄的人編不過，
而寫錯的人不會收到任何訊號。假想名字列在腳本頂端的 `ALLOW`，**每條都要附理由**，
比照 `apps/web/knip.ts` 的慣例。

圍欄程式碼區塊**預設整段跳過**（教學裡的 `modules/products/` 是刻意的假想範例），
但**目錄樹是例外**：樹住在圍欄裡就會整棵落進零覆蓋的盲區，所以樹要標記 ——
`<!-- check-docs: tree <base> -->` 會照縮排把每一項接回祖先再驗證存在，
`<!-- check-docs: tree - -->` 表示這棵樹是形狀示範、不對應真實檔案。
**沒有標記卻長得像樹的區塊會直接紅燈**，免得下一棵樹又靜靜回到零覆蓋。
另有 `<!-- check-docs: ignore-start -->`／`ignore-end` 給「這一節的主題就是某些檔案的
不存在」那類內容（移除模組的清單）用。

它還守一件**反方向**的事：`<!-- check-docs: commands check- -->` 標記的那個表格，
要恰好列出 `Makefile` 的 `TARGETS` 裡每一支 `check-*`。上面那些驗的是「文件指到的東西
存不存在」，而漏掉一整支指令不會讓任何連結斷掉 —— 檢查器照樣能跑，只是沒有人知道它在。
比對是雙向的：文件漏列一支會紅，文件多列一支（`TARGETS` 已經拿掉了）也會紅。
比對只認 `check-` 前綴，其餘指令不在它的守備範圍。

`check-acceptance` 是三層規格裡功能級那一層的檢查器：PR 描述的每一條驗收條件都要指名
一個真的存在的測試。它**不解析自然語言** —— 約束來自「必須指得出一個可執行的斷言」，
所以形容詞式的條件（「回應要快」）在寫測試名稱那一步就自己卡住了。只驗正方向
（驗收條件 → 測試），反方向刻意不做，理由寫在腳本頂端。

三件操作上要先知道的事。**測試還沒寫時它是紅的**，那是刻意的 —— 流程是先開 draft PR
寫驗收條件、再寫測試，所以它就是功能級的紅綠燈（見〈落點要在動手之前存在〉）。
**還沒有 PR 時它直接跳過**，所以本機在開 draft PR 之前跑它不會失敗。**逃生門是 PR 標題的
`[skip acceptance]`**，比照 `pr-checks` 裡 CHANGELOG 那一步的 `[skip changelog]`：純文件、CI 調整、相依升級
那類沒有行為變更的改動用它 —— 但要明講，而不是讓某個條件預設放行。

它順帶擋掉一件覆蓋率門檻擋不到的事：**驗收條件指名的測試被刪掉**。門檻是防退步的地板、
刻意訂得寬（見〈[覆蓋率門檻](#覆蓋率門檻)〉），刪掉幾支小測試照樣綠燈，
但那個名字一旦查無此人就是紅的。

`check-test-edits` 補的正是它擋不到的另一半：**保留同名測試、把裡面的斷言改鬆**。
它只看 PR 在 `tests/` 底下**刪掉的行**（純新增測試不攔，否則每個 PR 都攔一次，
很快就會被當成雜訊繞過），有刪就要求 PR 描述有一段「改動到既有測試」寫明原本那個斷言
為什麼是錯的。**它沒有 `[skip …]` 逃生門**：說明本身就是逃生門，合理的情況一句話就過，
寫不出那一句的時候正是要攔的時候。規則見〈改到既有測試要說明〉。

`check-shell` 守的是這個 repo 裡唯一沒有型別檢查也沒有單元測試的語言：`make` 的指令實作
全是 shell，而 shell 出錯的方式最安靜（未加引號的變數在路徑含空白時才裂開、拼錯的變數名
展開成空字串）。刻意關掉的規則都在腳本裡就地寫明理由，比照 `knip.ts` 的慣例。

每個指令的實作都在 `scripts/<指令>.sh`，Makefile 只做名稱對應，所以這些指令也可以不經 make
直接執行（`./scripts/build.sh`），從任何目錄呼叫都可以。共用的 compose 旗標、`.env` 載入與
確認提示在 `scripts/lib/`。**新增指令＝加一支 `scripts/<name>.sh`（記得 `chmod +x`）並把
`<name>` 加進 Makefile 的 `TARGETS`** —— 漏了後者不會報錯，只是 `make <name>` 說找不到目標。

### 相依升級紀律

相依由 dependabot 每週開 PR，多數直接合。跨 major 或一次升一批時，照這四條：

1. **遇到 peer／相容性阻擋就停在最新的相容版**，不要用 `--force`／`--legacy-peer-deps`
   或 `uv lock --frozen` 之外的手段繞過去。繞過去的代價是把「裝得起來」與「能用」分開，
   而 CI 只驗得到前者 —— 真正的錯會延到某個沒人跑到的程式路徑上。
   停在相容版不是欠債，是**已知且有記錄**的狀態。
2. **停下來的地方要就地寫下「為什麼停」與「移除條件」**，寫在 manifest 或設定檔本身，
   不要寫在文件裡（下一個要升級的人看的是 manifest）。移除條件要是**一行可以執行的指令**，
   不是「等以後」。現有的兩個例子：

   | 停在哪 | 卡點 | 寫在哪 |
   |---|---|---|
   | ESLint 9.x | `eslint-plugin-react` peer 只到 `^9.7` | `apps/web/eslint.config.mjs` |
   | TypeScript 5.x | `openapi-typescript` 要 `^5.x`、`typescript-eslint` 要 `<6.1.0` | `apps/web/package.json` 的 `//devDependencies` |

   **這張表只放「有卡點」的釘法。** 卡點消失就升上去、把那一列拿掉；沒有卡點卻仍然釘住的
   （例如 Python 釘在單一 minor），理由寫在它自己的 manifest 檔頭，那裡才是 owner。

3. **跨 major 升完，要跑的不只是 `make check`。** `check` 完全不涵蓋部署那一層，
   請另外驗：`make audit`（相依有沒有帶進新 advisory）、兩個 production image 建得起來、
   以及整套 `make dev` 起得來（healthcheck 鏈、備份還原、migration）。
   升 PostgreSQL 的 major 還要多一步：資料目錄格式與 major 綁死，新版 server 直接讀舊的
   `PGDATA` 會拒絕啟動，必須 `pg_dump` →換版本→ `pg_restore`（或 `pg_upgrade`）。
   這對已部署的下游是破壞性動作，升級步驟要寫進
   [`../CHANGELOG.md`](../CHANGELOG.md) 的那一筆條目。
4. **跨 major 的升級要自己補 CHANGELOG 條目。** dependabot 開的 PR 標題一律帶
   `[skip changelog]`（設定在 [`../.github/dependabot.yml`](../.github/dependabot.yml)，
   理由寫在那裡），所以 CI 的 `pr-checks` 不會提醒你。minor/patch 本來就不需要條目，
   但跨 major 對下游是有事要做的 —— 往 dependabot 的分支上推一個 commit 補進去。
   這不算額外負擔：規則 3 已經要求跨 major 升完要另外驗部署那一層，人本來就得停下來。

## 3. 分支與提交規範

Commit message 與分支名共用**同一份 type 清單** ——
[Conventional Commits](https://www.conventionalcommits.org/zh-hant/v1.0.0/) 的十個 type：

| type | 用在 |
|---|---|
| `feat` | 新功能 |
| `fix` | 修 bug |
| `docs` | 只動文件 |
| `style` | 不影響行為的排版：換行、空白、引號 |
| `refactor` | 不改行為也不加功能的重整 |
| `perf` | 效能 |
| `test` | 只動測試 |
| `build` | 建置本身：Dockerfile、compose、建置設定 |
| `ci` | `.github/` 與 `scripts/check-*.sh` |
| `chore` | 以上都不是的雜項，**相依升級也算這個** |

- Commit：`<type>: <祈使句>`，例 `feat: add product list page`
- 分支：`<type>/<kebab-case 描述>`，例 `feat/product-list`

共用同一份清單是為了不必記兩套詞彙 —— 所以分支寫 `feat/` 不是 `feature/`、`fix/` 不是
`bugfix/`，而升相依開的是 `chore/`，跟 [`../.github/dependabot.yml`](../.github/dependabot.yml)
產生的 `chore(deps)` commit 對得上。dependabot 自己開的分支叫 `dependabot/*`，
那是它產生的，不受這條管。

PR 送出前必須通過 `make check`（lint → typecheck → test → build）。

**這一節裡只有最後那條有東西在守。** `make check` 的內容 CI 的 `api` 與 `web` job 會再跑
一次，本機漏跑只是晚一點發現；但**分支命名與 Conventional Commits 沒有任何檢查器**
（沒有 commitlint，也沒有對應的 CI job），純靠自律。這是刻意的取捨 —— 這兩條的違規在
review 時一眼看得出來，為它們多養一個工具與一份設定不划算。

### CHANGELOG 條目

動到 `apps/`／`scripts/`／`infra/` 卻沒在 [`../CHANGELOG.md`](../CHANGELOG.md) 留一筆時，
CI 的 `pr-checks` 會擋。

**條目只寫改了什麼。** 功能怎麼用、為什麼這樣設計，一律留在 owner 文件
（[`../README.md`](../README.md)、`docs/`、[`../contracts/README.md`](../contracts/README.md)），
這裡只放連結。

**日常條目寫進 `## [Unreleased]`。** 那個標題不是版號，`make check-version` 取的是它下面
第一個版號標題 —— 所以條目可以一直累積，不必為了讓檢查器過而先決定版號。發版時把
`## [Unreleased]` 改名成該版號與日期，並在上面補一個新的空 `## [Unreleased]`；
發版 PR 還要改哪幾樣見 [`operations.md`](operations.md#發版與回滾)。

格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，版號採
[語意化版本](https://semver.org/lang/zh-TW/)。

**變更紀錄只有一份，刻意不拆成「模板的」與「專案的」兩份。** 拆開是為了讓模板與用它開出來
的專案能持續寫進同一條血脈而不衝突 —— 但快照模式下同一時間只有一個 owner
（見 [`TEMPLATE.md`](../TEMPLATE.md) 第 0 節），拆開就只剩成本：`make check-version`
要先判斷「這個 repo 是模板還是新專案」，CI 的守衛也要往兩個方向各擋一次。

### 分支保護與 CI 的紅綠燈

「PR 送出前必須通過 `make check`」與整套 CI，**沒有任何東西讓它變成強制** ——
沒有啟用分支保護時，PR 上的 job 全紅也 merge 得進去。補上這件事要在 GitHub 那一側
匯入 ruleset，連同 repo 的四個安全掃描開關，都是版控裡看不到的設定 ——
清單、指令與各自擋得住什麼見 [`ci-cd.md`](ci-cd.md#分支保護)。

**這裡只留一個對日常開發有影響的結論**：ruleset 沒有匯入時，下一節那幾分鐘就是
整條流程裡唯一真的擋得住東西的關卡。

### 取消 draft 之前：自己讀一次 diff

上面那句「沒有任何東西讓它變成強制」有一個直接的後果：**整條流程裡唯一的人類檢查點，
就是你在取消 draft 之前的那幾分鐘。** PR 上那一排 job 全是機器，而在沒有啟用分支保護時，
它們一個都擋不住 merge。

所以取消 draft 之前，到 PR 的 Files 分頁把整份 diff 從頭讀一次 —— 是**讀 diff**，
不是回想自己寫了什麼。跟 agent 一起做的改動特別需要這一遍：測試全綠、每個 gate 全過，
跟「這份 diff 是你要的東西」是兩件事。

判準清單在 [`../.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md)
的「取消 draft 前」那一段。其中一條機器守不住：實作途中發現驗收條件當初寫錯時，
`check-acceptance` 抓不到 —— 它只驗「指得出一個存在的測試」，那個測試確實存在、確實會過，
只是那條驗收條件描述的已經不是你做出來的東西。

**這一節刻意沒有檢查器**，同分支命名與 Conventional Commits。多一個人之後把
`required_approving_review_count` 調高，這一節就由真正的 review 取代。

## 4. 測試

```bash
cd apps/api && uv run pytest tests/ -v    # 後端
cd apps/web && npm test                   # 前端
```

兩邊的測試都放在該 app 的 `tests/`，與原始碼同構（`tests/modules/<name>/` 對
`modules/<name>/`）；目錄規則見 [`architecture.md`](architecture.md#前後端對照)。
兩邊都只掃 `tests/`（後端 `testpaths`、前端 `vitest.config.ts` 的 `include`），
**放在別處的測試不會執行也不會報錯**。

後端部分整合測試（游標分頁、bootstrap 的併發與交易回滾）需要連得到 PostgreSQL；
本機沒有時會自動 skip，也可以用 `uv run pytest -m "not integration"` 明確略過。CI 上會真的跑。

CI 有哪些 job、各自守什麼、哪個階段跑哪些，見
[`ci-cd.md`](ci-cd.md#ci-有哪些-job各自守什麼) —— 那份是 GitHub 那一側的 owner。
這裡只講一件跟寫測試直接有關的事：**`api` 與 `web` 只在 PR 與 tag 上跑**，
merge 到 `main` 那一輪不重跑，所以「等 merge 之後再看紅綠燈」不是一個選項。

### 覆蓋率門檻

門檻分別在 `apps/api/pyproject.toml` 的 `fail_under` 與 `apps/web/vitest.config.ts` 的
`coverage.thresholds`。

**這些數字是防退步的地板，不是目標。** 訂法是「量出現況，再往下留餘裕」，所以請不要為了把
數字推高而寫沒有價值的測試；補了有意義的測試之後，歡迎把門檻一起往上帶。
後端門檻刻意訂得能讓「本機沒有 PostgreSQL、integration 測試自動 skip」的情況也通過。

### 安全 advisory

**不允許直接忽略。** 確認某條 advisory 在本專案不可達時，請在該處留下
「advisory ID + 不可達的理由 + 到期複查日」，而不是把它從掃描範圍拿掉。

**掃描範圍刻意只到相依套件。** `make audit` 與 CI 的 security job 查的是 npm／uv 相依的
已知漏洞，**沒有**機密掃描，**也沒有**原始碼的靜態安全分析。那兩類在這個 repo 走 GitHub
那一側的開關（secret scanning + push protection、CodeQL default setup），不佔 workflow
也不進版控 —— 開法見 [`ci-cd.md`](ci-cd.md#repo-設定裡的安全掃描)。

版控裡那一層仍然只有 [`../.gitignore`](../.gitignore) 的 `.env*` 規則
（連同 `!.env.example` 那個例外），而它是**唯一在沒有網路、沒有 GitHub 的情況下也成立的
那一層** —— 放寬它之前請先想清楚，`make init` 產生的 `.env` 裡是真的金鑰。

**掃描有排程，不是只跟著 PR 跑。** advisory 資料庫是外部的，它會因為「今天有人公布了
新漏洞」而變紅 —— 那跟有沒有人送 PR 無關。所以 `ci.yml` 除了 push 與 pull_request，
還有一條每週一的 `schedule`。少了它，一個上線後穩定、幾週沒有 PR 的專案就是幾週沒掃過，
而 dependabot 只在**有更新時**才開 PR，補不上沒有更新的那幾週。
**排程只跑 `security` 一個 job**，其餘全部帶條件跳過（所以不會推任何 image）。

## 5. 寫文件與註解的慣例

這個 repo 的註解寫的是**為什麼**，不是做了什麼——尤其是「為什麼不用另一種看起來更自然的做法」。
新增取捨時請照這個標準寫，不要留下只是複述程式碼的註解。

**註解、docstring 與文件一律繁體中文**，前後端都是。技術名詞（`manifest`、`resolver`、
`route adapter`）保持原文不硬翻。唯一的例外是程式碼本身——識別字、字串常數與範例程式碼
照原樣。沒有檢查器在守這條，混用時最先壞掉的是同一份檔案裡的分節註解與 docstring 首行。

**而且要精準。** 一個取捨寫一段，講完就停；註解的長度要跟它防止的錯誤成本相稱——
會讓人靜靜踩坑的地方值得寫五行，一眼看得出來的東西一行都嫌多。鋪陳、免責、把同一件事
換句話說再講一次，都會稀釋掉旁邊那些真的重要的警告。

文件同理，另外還有五條：

1. **一個主題一個 owner 文件**，其他地方只放單向連結。不要出現「詳見 X／簡版見 Y」的互指，
   那會讓兩份都沒人敢刪，然後各自飄。
2. **規則可以重複一行，理由只寫一次。**「改了 schema 要跑 `make gen-types`」該出現在動作發生
   的每個位置；但「為什麼契約要進版控」只寫在 [`../contracts/README.md`](../contracts/README.md)。
3. **不寫這個 repo 自己的演進史。**「以前是…改成…」一律只留在
   [`../CHANGELOG.md`](../CHANGELOG.md)。
   這條**不包含**「為什麼不用另一種做法」—— 那是上面那個標準，要保留。
   只清「我們變過」，不清「我們考慮過」。
4. **可由指令取得的清單不抄進文件。** 例如 `make help` 已列出全部指令，文件只解釋
   非顯而易見的那幾個。抄一份的下場是它會落後於 `Makefile` 的 `TARGETS`。
5. **範例一律指向 repo 內真實檔案**（`modules/roles/`、`scripts/migrations/_example.py`），
   不另造一份會腐爛的假範例。但指向**範例模組**（刻意可刪的那個，見 `TEMPLATE.md` 第 2 步）
   要多想一步：下游刪掉它之後那些指路就懸空了。示範**規則**時請挑不會被刪的模組，
   範例模組留給「複製這個當起手式」那類指路。`make check-docs` 會把懸空的列出來。

## 6. 程式碼風格

底下每一條要嘛被檢查器擋下來，要嘛寫在這裡。**不會有「只存在於某人腦中」的風格規則。**

### 規格與測試的三層

「先寫的那個測試是規格」在這個 repo 是**三層**，因為多數改動是跟 AI agent 一起做的，
而 agent 會照著它讀得到的規格走 —— 規格沒有落點，它就只能照你當下那句話猜。

| 層 | 是什麼 | 誰在守 |
|---|---|---|
| **專案級** | [`../AGENTS.md`](../AGENTS.md) 的硬規則、`make help` 列出的那排 `check-*` 與前端的 `check:*`、[`../contracts/openapi.json`](../contracts/openapi.json) | 檢查器。**這一層是可執行的規格**，違反了會紅燈，不必倚賴誰記得 |
| **功能級** | 這次要做什麼、做完長什麼樣。寫在 PR 描述的「驗收條件」欄（[`../.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md)） | `make check-acceptance`：每條驗收條件都要指得出一個真的存在的測試 |
| **實作級** | red-green-refactor：先寫測試、看它失敗、寫剛好讓它過的實作、再重構 | 覆蓋率門檻（防退步，不是目標） |

功能級那一層**刻意不落成檔案**。`docs/specs/<feature>.md` 那種目錄的問題是它會腐爛：
功能上線之後沒有人再讀它，但它會一直待在 `docs/` 裡誤導下一個人。
驗收條件的長期歸宿是**測試名稱** —— 前端寫成讀得通的中文句子（`未登入導向 /login`），
後端寫成 `test_<動作>_<條件>_<結果>`（`test_get_users_without_permission_returns_403`）。
PR 描述留在 git 歷史裡，測試留在 `tests/` 裡，兩者都不需要有人維護。

**為什麼不用 BDD 工具鏈**（pytest-bdd、Gherkin、`.feature` 檔）：Gherkin 的價值是讓不寫程式的人
也能寫規格。這個 repo 的規格是你寫、agent 讀的，而 agent 讀自然語言驗收條件的能力遠好過讀
Gherkin；換來的 step definition 層則是純粹的維護成本 —— 每個 step 要對應一個函式，
而 step 一旦開始重用就會在不相干的情境之間長出耦合。所以**命名慣例借 BDD，工具鏈不引入**。
（e2e 是另一回事：它不是規格的表達方式，是**跨層接縫**的測試，範圍見〈e2e 的範圍〉。）

#### 落點要在動手之前存在

功能級那一層的價值是**在動手之前**把「做完長什麼樣」講定，所以它的落點必須在那個時間點
就已經存在。PR 描述滿足「不會腐爛」那一半 —— merge 完就沉進歷史，沒有人要維護它 ——
但它預設的建立時機是**動手之後**，於是 agent 開始工作時落點是空的，只能照你當下那句話猜。
那正是這一節開頭那句話要防的情況。

所以順序是**先開 draft PR，再寫程式**：

1. 開分支（`<type>/<kebab-case 描述>`，見〈分支與提交規範〉）
2. 推一個空 commit，開 draft PR，只填「這個 PR 做什麼」與「驗收條件」兩段。
   **commit message 帶 `[skip ci]`**：

   ```bash
   git commit --allow-empty -m "chore: 開 PR [skip ci]"
   ```

   那一刻的 tree 跟 `main` 位元組相同，而 `main` 那份剛剛才被 merge 的 CI 驗過 ——
   跑一輪的資訊量是零，卻要花掉整整一輪的分鐘數。

   **為什麼是 commit message 而不是 `ci.yml` 的條件**：workflow 只看得到事件型別，
   要它自動跳過就得寫成「`opened` 且是 draft 就不跑」，而那條規則會跟
   「Ready for review 不重跑」交出一條沒人驗過的路徑（從一個已經有 commit 的分支開
   draft PR、中途不推東西、直接按 Ready）。差別在**搞錯時往哪邊倒**：`[skip ci]` 忘了寫
   是多花八分鐘，自動條件判斷錯是該驗的沒驗 —— 而分支保護在免費方案是關的，
   缺少的 check 不會擋 merge，那個洞是靜默的。
   而且「這個 tree 是空的」本來就只有推 commit 的人知道。

   同一招也適用第 4 步「看它紅」的那一次 commit（CI 必紅，而你本機已經知道了）。
   **只用在那一次** —— 後面一定還會有 push 或按 Ready 把檢查補回來。

   > **要在 commit message 裡「提到」這個標記時，不要寫出它的字面值。**
   > GitHub 掃的是整段 commit message，不是只有第一行 —— 一個內文在解釋
   > 「為什麼用這個標記」的 commit 會把自己也跳過，而症狀是 PR 上
   > **一個 check 都沒有**（不是紅燈，是空的），看起來像 Actions 壞了。
   > 要在 commit 裡提它就寫成「skip ci 標記」這種不帶方括號的形式。
   > 同一組關鍵字還有 `[ci skip]`、`[no ci]`、`[skip actions]`、`[actions skip]`。
   > 文件與 PR 描述不受影響，只有 commit message 會被掃
3. **動手之前**把驗收條件裡模糊的地方問掉，答案改寫回驗收條件 —— 不是留在對話裡
4. 寫測試 → 看它紅 → 寫實作 → 綠
5. 取消 draft —— 之前先自己讀一次 diff，見〈[取消 draft 之前：自己讀一次 diff](#取消-draft-之前自己讀一次-diff)〉

**不改成 `docs/specs/<feature>.md`**：上面那個腐爛的理由對任何長期存在的檔案都成立，
換容器不換判斷。draft PR 只是把既有落點的**建立時機**往前挪，沒有新增任何要維護的東西。

第 3 步才是這一層真正的產出。「這裡要不要分頁」「權限不足回 403 還是 404」這類問題，
在寫測試之前問掉的成本遠低於實作走到一半才發現；而答案沒有改寫回驗收條件的話，
下一個讀這個 PR 的人 —— 包括下一次 agent 的對話 —— 拿到的還是模糊的那一版。

agent 讀這個落點的方式是 `gh pr view --json body -q .body`。

#### 哪些程式碼要 test-first

**適用範圍刻意不是全部。** `apps/web/vitest.config.ts` 與 `apps/api/pyproject.toml` 已經
標出哪些程式碼值得測，TDD 就套用在那些地方：

| 要 test-first | 不寫執行期測試 |
|---|---|
| `shared/**`（前後端都是） | 前端 `modules/*/actions.ts`：帶 `"use server"` 的薄包裝 |
| 前端 `modules/*/capabilities.ts` | 前端 `modules/*/ui/*.tsx`：畫面組裝 |
| 前端 `proxy.ts` | route adapter（改由 `tests/app/route-adapters.test.ts` 靜態守住） |
| 後端 service 與 repository | |

右欄的理由寫在 `vitest.config.ts` 的 `coverage.include` 註解裡：那些檔案真正會出錯的是
URL 與 payload 形狀，而那兩者由 OpenAPI 產生的型別在**編譯期**就擋掉了，寫執行期測試
只是在測 mock。**不要為了提高覆蓋率數字去補那種測試。**

畫面裡真的有分支時，把分支抽進 `capabilities.ts`（有測試）再回頭用，
例見 `modules/users/capabilities.ts` 與 `tests/modules/users/capabilities.test.ts`。

#### 改到既有測試要說明

**改程式不改測試。** 測試變紅時預設它是對的 —— 紅燈的意思是實作跟規格對不上，
而實作級的規格就是那個測試。把測試改成會過的樣子，等於把規格改寫成「實作現在的行為」：
紅燈消失，規格也一起消失。這是跟 AI agent 一起開發時最常見、也最安靜的失敗模式。

真的要改的時候（介面改名、相依升級換掉 mock、那條斷言從一開始就寫錯），在 PR 描述加一段
「改動到既有測試」，寫明**原本那個斷言為什麼是錯的** —— 不是寫你改了什麼（那看 diff），
是寫原本那條為什麼不該成立。`make check-test-edits` 會攔下沒有這一段的改動。

**它沒有 `[skip …]` 逃生門**，那是刻意的：說明本身就是逃生門。合理的情況寫一句就過得了，
而寫不出那一句的時候，正是要攔下來的時候。

#### e2e 的範圍

`e2e/` 底下的 playwright 測試（`make e2e`）**只測跨層接縫**。判準是一句話：
**單層測得到的東西一律不進來。** 新增一個 e2e 案例之前先回答「這條為什麼 vitest 或
pytest 測不到」—— 答不出來就寫在那一層。

不設這條上限的話它會長成第二套測試套件，然後因為慢又不穩而沒有人看 ——
那時候「e2e 不值得」才會變成真的。

目前守的四條，共同點是**兩邊各自都測過、中間沒有人測**：

| 接縫 | 單層測了什麼 | e2e 補什麼 |
|---|---|---|
| 一次性初始化 | 後端測併發與 transaction 回滾、前端測導向判斷 | 沒有人走過瀏覽器 → `/signup` → `REGISTER_KEY` → 登入 整條 |
| 路由保護 | `tests/proxy.test.ts` 測那個函式的邏輯 | 沒有人證明 **Next 真的載到了 `proxy.ts`**（放錯位置不會報錯，那一層會安靜地不存在） |
| WebSocket | 後端測事件與訊息、前端測窮盡處理 | 沒有人證明事件真的從後端流到畫面 |
| 跨前後端 i18n | 後端測 `resolve_text`、前端測字典 | 沒有人證明切語系之後**後端送來的訊息**跟著變 |

後兩條是同一個架構特性的兩面：型別由後端產生、前端消費。`api-types-up-to-date` job
證明兩邊的**型別**對得上，證明不了兩邊的**行為**接得起來。

**還沒守到的**：權限那一條（無權限帳號在 UI 上看不到、打 API 拿到 403）。它需要先建出
第二個受限帳號，那段流程比其他四條長一截。這是已知的缺口，不是判斷它不重要。

**e2e 應該由人寫，不要交給 agent。** 它是這個 repo 裡唯一能量到「agent 把可見測試
逐一寫綠、但功能組合起來是壞的」的層 —— 因為它斷言的是使用者可見行為，可以直接從驗收
條件推導，不必讀任何單元測試。agent 自己寫的話那個獨立性就沒了。
**這一條沒有檢查器在守**，同分支與提交規範。

#### 什麼時候跑 e2e

| 時機 | 跑不跑 |
|---|---|
| 存檔、改一行 | 不跑。它是分鐘級的，也不在 `make check` 裡 |
| 動到**跨層**的東西 | 本機跑一次 —— WS 事件、後端送到畫面的文字、認證／session／`proxy.ts`、bootstrap、compose 或 nginx 的接線 |
| 動到單層 | 不必，那一層的單元測試就夠了（同上面那條範圍紀律） |
| 開 PR | CI 會跑，本機跑不跑隨你 |
| 合併進 `main` | **不跑** —— PR head 的 tree 就等於 merge 後的 tree（靠 ruleset 的 strict 政策撐住），重跑是零新資訊。沒匯入 ruleset 的話這個推論不成立，見 [`ci-cd.md`](ci-cd.md#分支保護) |
| push `v*` tag | 跑 —— 發版的 image 也要通過跨層驗證 |
| 每週排程 | **不跑**。那條 cron 存在的理由只有 `security` job；e2e 的相依全部釘死，每週跑測不到新東西 |

CI 的 `e2e` job 失敗時會把 `playwright-report` 上傳成 artifact。**但「判斷」跟「擋得住」
是兩件事**：它要擋得住 merge，前提是 `.github/rulesets/main.json` 真的匯入了 GitHub ——
沒匯入的話 e2e 紅了照樣 merge 得進去（同其他所有 job，見〈分支保護〉）。

#### 怎麼跑

`e2e/package-lock.json` 隨專案納入版控，`make e2e` 會依它執行 `npm ci` 安裝相依；
從模板開案不需要另行產生 lock 檔。

`make e2e` 用自己的 compose project name，跟 `make dev` 完全隔離 —— 開發環境跑著的時候
也可以跑，而且它每次都會清掉**自己那份**資料庫（第一條接縫需要一個還沒初始化的系統）。

**它不固定佔用任何 port。** nginx 那邊寫的是 `ports: ${SYSTEM_PORT:?}:80`，沒辦法不
publish，所以 `scripts/e2e.sh` 把 `SYSTEM_PORT` 蓋成 `0` 讓作業系統配一個沒人用的臨時
port，跑完就還回去。同時開好幾個專案跑 e2e 也不會撞，也不會像 `make dev` 那樣長期佔著
一個號碼。實際配到哪個由腳本問 `compose port nginx 80` 得知並印出來。

**e2e 的型別檢查是 `make e2e` 的一步，不在 `make typecheck`。** 那支要能離線快跑，而
e2e 這邊本來就已經 `npm ci` 過了。代價是 e2e 的型別錯誤要到 `make e2e` 才浮出來。

留下環境事後查看用 `E2E_KEEP=1 make e2e`，它會印出對外位址。

**看著它跑用 `E2E_HEADED=1 make e2e`。** 會開一個真的 Chromium 視窗、把每個動作放慢到
人眼跟得上，整條走完（註冊 → 登入 → 建項目 → WS 通知 → 切語系）。放慢的幅度用
`E2E_SLOWMO` 調（毫秒，預設 300；`E2E_SLOWMO=0` 就是全速的 headed）。

單支測試的 timeout 會**跟著放慢一起放大**（`playwright.config.ts` 的
`90_000 + slowMo * 200`）。那 90 秒的底是照 `next dev` 的編譯時間訂的，沒有含放慢那一筆
—— 不放大的症狀是「headed 跑到一半 timeout，換回 headless 就過」。

**CI 上這個變數會被忽略**（clamp 在 `playwright.config.ts`）：runner 沒有顯示器，
而 headed 不改變任何斷言，讓整個 job 為一個顯示偏好紅掉沒有意義。

`scripts/e2e.sh` 之後的參數會原樣轉給 playwright：

```bash
./scripts/e2e.sh --headed             # 同 E2E_HEADED=1 make e2e
./scripts/e2e.sh --grep 英文          # 只跑標題含「英文」的那條接縫
./scripts/e2e.sh tests/items.spec.ts  # 只跑一支
```

`--grep` 比對的是**測試標題**（都是中文，見 `e2e/tests/`），比對不到會得到
`No tests found` 而不是靜靜跑零條。挑一條接縫來跑是安全的 —— `bootstrap` 是
`seams` 的 project 相依，playwright 不會把它一起濾掉，所以登入狀態一定備得起來。

**`make` 不轉發參數** —— Makefile 只做「指令名稱 → 腳本」的對應（見它的檔頭）。所以走
make 的那條路一律用環境變數，跟 `E2E_KEEP` 一致；要帶旗標就直接呼叫腳本。

**失敗時看哪裡。** CI 的 `e2e` job 失敗會把三份東西打包成 `e2e-failure` artifact：

| 檔案 | 什麼時候有用 |
|---|---|
| `playwright-report/` | html 報告：哪一條失敗、每一步的細節 |
| `test-results/` | trace 與截圖（`trace: retain-on-failure`），`npx playwright show-trace` 打得開 |
| `e2e/test-results/docker-logs.txt` | **stack 根本沒起來時，只有它講得出原因** |

最後一列是刻意的：stack 起不來的話 playwright 一步都沒跑，前兩份是空的，畫面上只有一個
紅燈和「暖機超時」，而真正的原因（migrate 失敗、web 編譯失敗、環境變數少
一個）只在容器 log 裡。所以 `scripts/e2e.sh` 的 teardown 會在**收掉環境之前**先把 log
倒進 `test-results/` —— 收掉之後就沒得問了。

PR 上另外會有 inline annotation（`github` reporter）直接標在失敗的那一行。

**playwright 刻意跑在 host 而不是 compose 裡的一個服務**（那是下一個人會想試的做法），
四個理由寫在 [`../scripts/e2e.sh`](../scripts/e2e.sh) 的檔頭。

### 單行 100

| | 工具 | 「100」怎麼算 |
|---|---|---|
| 前端 | ESLint `max-len` | **字元數**（中文一字算 1） |
| 後端 | ruff `E501` | **顯示寬度**（中文一字算 2） |

兩邊不一致是工具的既有行為，沒有為此另造檢查器：實測前端超過 100 字元的行**沒有一行是
註解**，中文註解本來就被折在 90 欄左右，為個位數的行寫一支自訂寬度檢查器不划算。
寫中文註解時看顯示寬度就好，兩邊都會過。

前端**豁免字串、樣板字串、URL 與 regex**：i18n 的英文譯文本來就長，硬折成字串串接
只會多出雜訊而不會更好讀。代價是「一行裡只要有字串就整行不檢查」——那是 ESLint
`ignoreStrings` 的行為，知道就好。

### 整潔性：量化上限

| 規則 | 前端（`.ts`） | 前端（`.tsx`） | 後端 |
|---|---|---|---|
| 巢狀深度 | `max-depth` 4 | 同左 | — |
| 循環複雜度 | `complexity` 10 | 15 | `C901` 10 |
| 函式長度 | `max-lines-per-function` 60 | 100 | `PLR0915` 40 敘述 |

三件要知道的事：

1. **`.tsx` 放寬不是因為畫面可以比較亂**，而是這兩個指標對 JSX 失真：條件渲染的 `&&`
   與三元運算每一個都計進複雜度，JSX 本身也讓元件輕易破百行，而那些行不是邏輯。
2. **測試檔不受函式長度限制**：`describe(...)` 的回呼是分組而不是一個有邏輯的函式。
   複雜度仍然套用——測試裡出現分支才是真的該警覺的事。
3. **這些是防退步的地板，不是重構目標**（同覆蓋率門檻，理由見
   〈[覆蓋率門檻](#覆蓋率門檻)〉）。
   想收緊請先重構再把數字帶下來，不要為了讓數字好看而硬拆函式。

### 整潔性：死碼

前端 `npm run check:deadcode`（knip）擋未使用的檔案、匯出與相依套件。
例外寫在 `apps/web/knip.ts`，**每一條都附理由**。

它的 `entry` 刻意用「架構文件定義的公開面」而不是逐條忽略：模組的 `public.*`、
UI kit 的 `shared/ui/index.ts`、契約型別目錄 `shared/api/entities.ts` 這些的存在
不需要「repo 內部有人用」來證成——下游專案才是使用者。

**後端沒有對等的工具。** ruff 的 `F401` 只涵蓋未使用的 import，跨模組的死碼
（沒人呼叫的 service 函式、沒人用的 schema）目前只能靠 review 發現。

### 整潔性：不進檢查器的部分

這幾條沒有工具擋，靠 review：

- **一個函式一件事。** 需要用「而且」才能描述它在做什麼，就是該拆的訊號。
- **早退出。** 前置條件不成立就 `return`，不要把主線邏輯包進一層層的 `else`。
  `modules/users/ui/EditUserDialog.tsx` 的 `getEditableFields` 是這個寫法的例子。
- **命名見義。** 讀不出意圖的長布林運算式要給它一個名字——順帶一提，這通常也是
  複雜度上限會抓到的東西。
- **不留死碼。** 註解掉的程式碼、「之後可能會用到」的分支一律刪掉，它們在版控裡。
