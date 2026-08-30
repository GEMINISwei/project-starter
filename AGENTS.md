# 給 AI agent 的專案指引

這份檔案是**內容本體**。根目錄的 `CLAUDE.md` 之類的工具慣例檔只是把它接進來的**轉接檔**，
按你用的工具增刪即可 —— 規則不要寫進轉接檔。

這份檔案只寫**無法從程式碼推導**的規則。細節不要複製到這裡，指向原始文件就好：

- [`docs/architecture.md`](docs/architecture.md)：**規則** —— 依賴邊界、模組介面、目錄結構、移除模組
- [`docs/development.md`](docs/development.md)：**流程** —— 本機開發、`.env`、指令、提交規範、測試、文件慣例、程式碼風格
- [`docs/design-system.md`](docs/design-system.md)：**樣式** —— token 分層、主題、導入外部 DS、CSS 檢查器
- [`docs/extending.md`](docs/extending.md)：**教學** —— 新增頁面／模組／權限／WS／migration／Seed
- [`docs/operations.md`](docs/operations.md)：**運行** —— 部署、帳號初始化、Session 撤銷、限流
- [`docs/ci-cd.md`](docs/ci-cd.md)：**GitHub 那一側** —— CI 的 job、分支保護、安全掃描開關、移除 CD
- [`contracts/README.md`](contracts/README.md)：前後端型別契約怎麼產生與消費

這個 repo 是 **GitHub template repository**：新專案用 "Use this template" 開出來，
拿到的是一份**快照**，沒有共同歷史，也沒有持續同步的上游。所以**下游可以改任何地方**，
包含 `shared/` 與組裝層 —— 那些檔案從被複製的那一刻起就屬於新專案。
為什麼不做成可同步的上游，見 [`TEMPLATE.md`](TEMPLATE.md)。

## 硬規則

前六條由檢查器擋下來（`npm run check:architecture`、`npm run check:tokens`、
`tests/test_architecture.py`），最後一條靠 review —— 但先知道比事後被退快：

1. **跨模組只走 public entry**：前端 `public.server.ts` / `public.client.ts`、後端 `public.py`。
   組裝層也一樣，沒有特權。
2. **模組內部一律相對路徑**（`./ui/UsersView`、`../types`）；`@/` 只用於跨層。
3. **UI kit 只從 `@/shared/ui` 匯入**，不可指進 `shared/ui/` 的子路徑。
   需要 kit 裡的某個 class 時，在 kit 裡多包一個元件，不要去 `composes:` 它的 CSS module
   （`composes:` 那一半由 `npm run check:tokens` 擋）。檢查器裡有**一條**寫死的例外
   （`app/layout.tsx` 載入的全域樣式表），理由見
   [`docs/architecture.md`](docs/architecture.md#強制依賴規則)；要加第二條之前先讀那一段。
4. **`shared/` 不可引用 `modules/` 或組裝層**。
5. **CSS 只能引用語意層 token**（`--color-*`、`--space-*`…），不可寫死色值、不可碰
   原始層 `--ds-*`。**`style={{…}}` 也算**，而且 PWA manifest 的 `theme_color` 要跟著
   主題底色走 —— 這兩個 CSS 以外的出口一樣由 `check:tokens` 擋。三層 token 的分界、
   主題與導入外部 DS 的流程見 [`docs/design-system.md`](docs/design-system.md)。
6. 前端模組：模組根放資料與規則，`ui/` 放畫面（元件、只服務畫面的 hook、CSS module）。
   不要在模組裡再開 `components/`、`hooks/`、`utils/`。
   每個模組都要有 `manifest.ts`、`i18n.ts` 與至少一個 `public.server.ts`／`public.client.ts`。
7. 後端 service 回傳**建構好的 pydantic model**，不是 dict，而且**一定要寫回傳型別註記** ——
   `modules.*` 沒有開 `disallow_untyped_defs`，漏寫註記那個函式就完全不受檢查。

## 寫程式的方式

規則與數字在 [`docs/development.md`](docs/development.md#6-程式碼風格)，這裡只列你動手前要知道的：

- **規格有三層，動手前先確認你在哪一層**：專案級（這份檔案的硬規則 + 那一整排檢查器，
  可執行、違反會紅燈）、功能級（PR 描述的驗收條件）、實作級（測試）。
  分界與「為什麼不引入 BDD 工具鏈」見
  [`docs/development.md`](docs/development.md#規格與測試的三層)。
- **先開 draft PR，再寫程式**：開分支 → 空 commit（帶 `[skip ci]`）→ draft PR 只填
  「這個 PR 做什麼」與「驗收條件」→ **動手之前把驗收條件裡模糊的地方問掉，答案改寫回
  驗收條件**（不是留在對話裡）→ 寫測試看它紅 → 實作到綠 → 取消 draft。功能級規格的價值
  在動手之前，落點就必須在動手之前存在。**一條驗收條件寫不出對應的測試名稱，
  代表它還沒被想清楚 —— 那就是要問的地方。**
  - 那個空 commit 的 tree 跟 `main` 位元組相同，跑一輪 CI 的資訊量是零，所以帶標記。
  - **但在別的 commit 裡「提到」這個標記時不要寫出字面值。** GitHub 掃的是整段 message、
    不是只有第一行，所以一個內文在解釋它的 commit 會把自己也跳過 —— 症狀是 PR 上
    **一個 check 都沒有**（不是紅燈，是空的），看起來像 Actions 壞了。要提就寫成
    「skip ci 標記」這種不帶方括號的形式。
- **先寫測試**（red-green-refactor）。但**不是每一層都要**：薄 wrapper
  （前端 `modules/*/actions.ts`）與畫面（`modules/*/ui/*.tsx`）刻意不寫執行期測試，
  畫面裡真的有分支時抽進 `capabilities.ts` 再測。**不要為了覆蓋率數字補測試。**
- **測試一律放該 app 的 `tests/`，與原始碼同構**（`tests/shared/access/permissions.test.ts`
  對 `shared/access/permissions.ts`），前後端同一套。兩邊都只掃 `tests/`，
  放在別處不會執行也不會報錯。測試不受依賴邊界規則管，可以直接指進被測目標。
- **單行長度、函式長度與複雜度都有上限**，全部由 lint 擋。數字不抄在這裡（會各自飄），
  要查看 `development.md`。只有一點要先知道：前端算字元、後端算顯示寬度（中文一字 2 欄），
  寫中文註解時看顯示寬度就好，兩邊都會過。
- **e2e 只測跨層接縫，而且不要由你來寫**。`e2e/` 底下守的是「前後端各自都測過、
  中間沒有人測」的那幾條（WS 事件流到畫面、切語系後端訊息跟著變…）。判準是
  「這條為什麼 vitest 或 pytest 測不到」—— 答不出來就寫在那一層。
  它是唯一能量到「可見測試逐一寫綠、組合起來卻是壞的」的層，agent 自己寫就沒有那個
  獨立性了。範圍與已知缺口見
  [`docs/development.md`](docs/development.md#e2e-的範圍)。
- **不留未使用的匯出**。只在自己檔案裡用到的函式與常數不要 `export`；
  `npm run check:deadcode` 會擋。例外寫在 `apps/web/knip.ts` 且**每條都要附理由**。

## 改動後一定要做的事

- **改了後端 schema／權限／WS 事件／語系／`APP_VERSION` → 跑 `make gen-types`**。
  忘了跑，CI 的 `api-types-up-to-date` job 會紅燈，而且前端拿到的是舊型別，錯誤會延到執行期。
  （`APP_VERSION` 常被漏掉：它是 OpenAPI 的 `info.version`，改了就是改契約。）
- 提交前跑 `make check`（lint + typecheck + test + build，前後端都跑）。
- 只想快速確認邊界：`cd apps/web && npm run check:architecture`；
  只想確認 token 與 CSS：`npm run check:tokens`；
  只想確認沒留下未使用的匯出：`npm run check:deadcode`。
- **改了 `.github/workflows/ci.yml` 或 `.github/rulesets/main.json` → 跑 `make check-ci`**。
  它守 CI 內嵌的指令與 `scripts/{lint,typecheck,test,build}.sh` 一致，以及（ruleset 存在時）
  分支保護涵蓋每一個會在 PR 上跑的 job。**新增 job 卻沒加進 ruleset 是完全沒有症狀的**：
  job 照跑，只是不再擋 merge。只在 push 上跑的 job（`publish`、`pushed-via-pr`）
  反過來**不能**列進去。改過 `main.json` 之後**要重新匯入 GitHub 才生效**，
  而且要用 `PUT` 不是 `POST`（`POST` 會多出第二份同名 ruleset，兩份疊加而且沒有任何提示）——
  指令見 [`docs/ci-cd.md`](docs/ci-cd.md#匯入-ruleset)。
- **shell 訊息裡的變數一律寫成 `${VAR}`**，不要 `"$VAR，中文"`。macOS 內建的 bash 3.2 會把
  後面的多位元組字元吃進變數名，`set -u` 當場報 unbound variable —— 而中招的通常是錯誤路徑，
  結果是最需要那行訊息時看到一句亂碼。`make check-shell` 會擋。
- **改了 `scripts/*.sh`、`.env.example`、compose、nginx 模板或任何 `.md` → 跑對應的
  `make check-shell`／`check-env`／`check-compose`／`check-nginx`／`check-docs`**。這五支不在 `make check` 裡
  （`check` 只涵蓋原始碼），它們在 CI 的 `deploy-config` job，
  本機不補跑的話會等到推上去才發現。`check-docs` 擋的是文件指向不存在的檔案、錨點或識別字，
  以及**反方向**的一件事：`docs/development.md` 的指令表要涵蓋 `TARGETS` 裡每一支 `check-*`
  （新增一支卻沒寫進文件，那支檢查器就沒有人知道它在）。
- **日常的 CHANGELOG 條目寫進 [`CHANGELOG.md`](CHANGELOG.md) 的 `## [Unreleased]`**
  （動到 `apps/`／`scripts/`／`infra/` 卻沒留條目時 CI 的 `pr-checks` 會擋）。
  升 `APP_VERSION` 時把 `## [Unreleased]` 改名成該版號，發版的 git tag 則是
  `v<APP_VERSION>`；三者由 `make check-version` 守（在 `deploy-config` job 裡）。
  發版 PR 要改哪四樣見 [`docs/operations.md`](docs/operations.md#發版與回滾)。
- **升級相依遇到 peer 擋住時，停在最新的相容版並就地寫下移除條件**，不要用
  `--force`／`--legacy-peer-deps` 繞過。四條規則見
  [`docs/development.md`](docs/development.md#相依升級紀律)。

## 容易踩的地方

- **route adapter 是薄 wrapper，且要把 Next 特有 export 一個個接上**：

  ```tsx
  import { XPage, generateXMetadata, type XPageProps } from "@/modules/x/public.server"
  export const generateMetadata = generateXMetadata
  export default function Page(props: XPageProps) { return <XPage {...props} /> }
  ```

  Next 只讀 route 檔的 export，漏掉一律**沒有錯誤訊息**。完整清單、理由與例外見
  [`docs/architecture.md`](docs/architecture.md#frontend-module-介面)；
  `tests/app/route-adapters.test.ts` 在守。
- **新增有導覽的模組，兩個安靜失敗的點**：`config/routes.ts` 的 `ENABLED_MODULES`
  漏了 → 沒有導覽也沒有 proxy 保護，但頁面照樣渲染；`app/(protected)/` 的 route adapter
  漏了 → 側欄連結 404。（`nav-icons.ts` 的 `NAV_ICONS` 也要加，但那個漏了會編譯失敗。）
- **每個使用者可見的字串都要有中英兩份**。字串放**擁有它的那一層**的 `i18n.ts`
  （模組放 `modules/<name>/i18n.ts`，UI kit 放 `shared/ui/i18n.ts`，組裝層放
  `config/i18n.ts`），沒有全站字典。漏翻譯會編譯失敗，所以不必記規則，記住位置就好。
  Server Component 用 `await getT()`、client 用 `useT()`、純函式收 `locale` 參數。
  **後端送到使用者眼前的文字（WS 事件訊息、推播內容）也一樣**，走 `LangText` +
  `resolve_text()`，由 `tests/test_i18n_text_usage.py` 擋掉直接寫死的字串。
  三個不走字典的例外（manifest 的 `label`、權限標籤、頁面標題）與加第三種語言的步驟，
  見 [`docs/extending.md`](docs/extending.md#語系i18n)。
- **`Permission`、`WsEventType` 與 `Language` 是刻意中央化的三份清單**，新增功能時要去改它們。
  這是為了換取前後端的靜態型別聯集，不要「順手」改成動態組裝。三者都各有一個
  「只是為了讓 enum 進 OpenAPI」的端點（`/permissions/`、`/ws/events`、`/languages/`），
  **看起來沒人呼叫不代表可以刪**。
- **docstring 會外流到公開 API 文件**：route function、進到 schema 的 pydantic model 與 enum，
  它們的 docstring 會進 OpenAPI 並被複製到前端型別檔。那三處只寫呼叫端需要知道的事，
  內部設計說明寫在模組層 docstring 或一般註解。
- 本機沒有 PostgreSQL 時，integration 測試會自動 skip
  （`uv run pytest -m 'not integration'`），CI 上會真的跑。
- **`.env.example` 是環境變數的唯一清單，新增變數要同步四處**（清單、`init.sh`、compose、
  `app/config.py`）。四處都由 `make check-env` 守著，但它**不在 `make check` 裡** ——
  記得自己跑一次。四處是哪些、各自守到什麼程度，見
  [`docs/development.md`](docs/development.md#環境變數的四個同步點)。
- **兩個 app 都沒有 `src/` 中間層**：後端 import root 是 `apps/api/`
  （`from modules.users.public import …`），前端 `@/` 指向 `apps/web/`。
  新增一層原始碼目錄要同步加進兩個檢查器的 `SOURCE_DIRS` / `PACKAGE_DIRS`，漏掉不會報錯 ——
  見 [`docs/architecture.md`](docs/architecture.md#目錄結構)。
- **前端不要用 `NEXT_PUBLIC_*` 放部署設定**。那一組會在 `next build` 當下內嵌成字面值，
  等於把設定烤進 image —— 改了主機 `.env` 畫面不會變，也沒有任何錯誤訊息。
  可以公開給瀏覽器的執行期設定走 `shared/runtime/`（server 端 `getPublicConfig()`、
  client 端 `usePublicConfig()`）。真的移不掉的 build 期值只有一個
  （`UPLOAD_SIZE_LIMIT`），它有開機自檢在守，見 `apps/web/instrumentation.ts`。
- **`apps/web/proxy.ts` 不能搬**。那是 Next 的根目錄慣例檔（Next 16 把 `middleware.ts`
  改名成它），只認 `<root>/proxy.ts` 或 `<root>/src/proxy.ts`。放錯位置**編譯不會報錯**，
  只是路由保護那一層安靜地不存在 —— `tests/proxy.test.ts` 也照樣綠，它測的是那個函式的
  邏輯，不是「Next 有沒有載到這個檔」。**唯一會紅的是 e2e**：`e2e/tests/proxy.spec.ts`
  就是為這條規則寫的斷言版。手動確認的話看 `npm run build` 的輸出有沒有
  `ƒ Proxy (Middleware)`。
- **compose 旗標不要自己組**。`--project-directory` 與 `--env-file` 的基準不同，組錯時
  docker **不會報錯**（bind mount 來源目錄會被默默建立）。唯一一份正確組合與完整理由在
  `scripts/lib/compose.sh` 的長註解，`make check-compose` 守它。
- **`make` 的指令實作全部在 `scripts/<指令>.sh`，Makefile 只是名稱對應表**。
  新增指令要加腳本、`chmod +x`，並把名稱加進 Makefile 的 `TARGETS`（漏了後者不會報錯，
  只是 `make <name>` 說找不到目標）。共用的 `.env` 載入、確認提示、compose 旗標在
  `scripts/lib/`；被 source 的檔案刻意不設 `set -e`，那是各腳本自己的事。

## 寫文件與註解的慣例

註解寫的是**為什麼**，不是做了什麼 —— 尤其是「為什麼不用另一種看起來更自然的做法」；
只複述程式碼的註解不要留。而且要**精準**：一個取捨一段，講完就停，長度跟它防止的錯誤
成本相稱。鋪陳與換句話說再講一次，會稀釋掉旁邊真正重要的警告。
文件另有五條規則（一個主題一個 owner、理由只寫一次、演進史只進 `CHANGELOG.md` 等），見
[`docs/development.md`](docs/development.md#5-寫文件與註解的慣例)。
