# 模組化架構

本專案以 monorepo 內部重用為目標，不把共用程式發布成 npm 或 Python 套件。前後端使用相同的三層概念：

```text
app → modules → shared
app → shared
```

- `app`：框架入口與組裝點，只決定啟用哪些模組及如何掛載。
- `modules`：完整的垂直功能，包含該功能的資料、規則、API／畫面與測試。
- `shared`：不認識業務名稱、可被多個模組使用的平台能力。

新增或移除功能的實際步驟見 [`extending.md`](extending.md)；這份文件只講規則與介面。

## 目錄結構

<!-- check-docs: tree . -->
```text
<project>/
├── apps/
│   ├── api/                    # FastAPI
│   │   ├── main.py             # 進入點（uvicorn 啟動器）
│   │   ├── app/                # config、server、registry、Permission enum
│   │   ├── modules/            # users、roles、permissions、languages、items、push、realtime
│   │   ├── shared/             # auth、db、http、time 通用能力 + module.py（manifest 契約）
│   │   ├── tests/              # 與原始碼同構，見「前後端對照」
│   │   │   ├── modules/                  # tests/modules/<name>/
│   │   │   ├── shared/                   # 對應 shared
│   │   │   ├── test_architecture.py      # 依賴邊界的靜態檢查
│   │   │   ├── test_i18n_text_usage.py   # 送到使用者眼前的文字要走 LangText
│   │   │   └── test_request_log.py
│   │   └── scripts/
│   │       ├── db.py                    # DB 管理 CLI
│   │       ├── export_openapi.py        # 產生 contracts/openapi.json
│   │       └── migrations/_example.py   # migration 撰寫範本（不會被執行）
│   │
│   └── web/                    # Next.js
│       ├── app/                # Next.js 薄層（page／layout／error），外加樣式層與
│       │                       # 幾個 Next 慣例檔：tokens/、themes/、globals.css、
│       │                       # manifest.ts、healthz/
│       ├── config/             # 組裝根：啟用模組、路由、導覽圖示、主題、WS handler、
│       │                       # 組裝層字串（i18n.ts）
│       ├── modules/            # auth、users、roles、items、settings、push
│       ├── shared/             # api、session、access、pagination、realtime、i18n、
│       │                       # runtime（執行期注入的公開設定）、ui
│       │                       # + module.ts（manifest 契約，對稱於後端 module.py）
│       ├── proxy.ts            # 路由保護中介層（Next 的根目錄慣例檔，不能搬）
│       ├── instrumentation.ts  # 開機自檢：build 期烤的設定與執行期的要一致
│       ├── knip.ts             # 死碼檢查的設定，例外每條附理由
│       ├── public/sw.js        # service worker，只服務推播
│       ├── tests/              # 與原始碼同構，另有兩個對應非原始碼目標的
│       │   ├── scripts/        # 兩支檢查器自己的 fixture 測試
│       │   ├── public/         # public/sw.js
│       │   └── setup.ts        # Vitest + jest-dom 測試環境設定
│       └── scripts/
│           ├── check-boundaries.mjs   # 依賴邊界與模組檔案放置
│           └── check-tokens.mjs       # 設計 token 與 CSS，見 design-system.md
│
├── contracts/openapi.json      # 由 api 產生、committed，是前端型別的唯一來源
├── infra/
│   ├── docker/                 # docker-compose.yml + .dev.yml + .prod.yml
│   └── nginx/templates/        # nginx 設定模板（envsubst）
├── scripts/                    # 每個 make 指令一支腳本，共用的部分在 lib/
└── docs/                       # architecture、development、design-system、
                                # extending、operations、ci-cd
```

兩個 app 都**沒有** `src/` 中間層 —— 目錄根就是程式碼根。後端的 Python import root 是
`apps/api/`（所以是 `from modules.items.public import …`），前端的 `@/` 指向 `apps/web/`。
少了 `src/` 這個天然邊界，「哪些目錄是原始碼」改成寫在兩個檢查器裡：
`apps/web/scripts/check-boundaries.mjs` 的 `SOURCE_DIRS` 與
`apps/api/tests/test_architecture.py` 的 `PACKAGE_DIRS`。**新增一層要同步加進去**，
漏掉不會報錯，只是那一層不再被邊界規則管。兩份名單都**不含 `tests/`**：邊界規則守的是
產品程式碼的依賴拓撲，測試可以直接指進被測目標。

`packages/` 刻意不存在：那個位置保留給真正跨 app 可重用的 library，而目前沒有任何東西符合
條件。契約（`contracts/`）是資料檔加上產生規則，不是 library，所以分開放 ——
理由見 [`../contracts/README.md`](../contracts/README.md)。

## 前後端對照

同名的目錄在兩邊不一定是同一件事，先看這張表再讀底下的規則：

| 概念 | 後端 | 前端 |
|---|---|---|
| 組裝根（決定啟用哪些模組） | `app/` | `config/` |
| 框架轉接層 | 無（FastAPI 由 `app/server.py` 直接組） | `app/`（Next.js 規定的 `page`／`layout`／`loading`／`error`，只做接線，見下方分級規則） |
| 垂直功能 | `modules/` | `modules/` |
| 平台能力 | `shared/` | `shared/` |
| 測試 | `tests/`，與原始碼同構（`tests/modules/<name>/` 對 `modules/<name>/`） | 同左 |

前端 `app/` 之所以和後端 `app/` 同名卻不同義，是因為那個名字由 Next.js 決定，不能改。
**前端真正對應後端 `app/` 的是 `config/`。**

`config/` 是**組裝根，不是建置設定** —— 它跟同在 `apps/web/` 根目錄的 `next.config.ts`、
`vitest.config.ts`、`eslint.config.mjs` 沒有關係，同名只是巧合。它之所以與框架轉接層
`app/` 分成兩個目錄（而不是收成 `app/_config/`），是因為 `routes.ts` 必須保持 edge-safe
（`proxy.ts` 會載入它，那裡沒有 React），跟滿是 React 的 `app/` 實體分開是一道輕微但實用的護欄。
兩者在依賴規則上仍是**同一層**：`scripts/check-boundaries.mjs` 的 `isComposition` 同時涵蓋兩個目錄。

功能的落點也不是每個都一對一。前後端都存在的模組一律同名（`users`、`roles`、`items`、`push`），
其餘的對照如下：

| 後端 module | 前端落點 | 為什麼 |
|---|---|---|
| `realtime` | `shared/realtime/` + `config/realtime/` | 前端這一側是連線殼層與事件表組裝，不是業務功能；各功能的事件處理仍留在自己的 `realtime.ts` |
| `permissions` | `shared/access/` | 前端只需要「判斷有沒有權限」這個純函式，沒有頁面也沒有資料 |
| 無 | `auth`、`settings` | 登入畫面與設定畫面是純前端功能；它們呼叫的是 `users` 與 `push` 的端點 |

## 強制依賴規則

1. `shared` 不可引用 `modules`、`app` 或前端的 `config`。
2. module 可引用 `shared`，但**不可反向引用組裝層**（前端 `app`／`config`、後端除
   `app.permissions` 這唯一一個例外以外的一切）。module 要拿到組裝層
   決定的東西，靠參數或 `app.state` 傳進來，不是自己去 import。
   那個例外是 `Permission` enum：它必須是所有 module 的聯集才能進 OpenAPI（見
   「三份刻意中央化的清單」）。manifest 的**契約**不在例外裡 —— 它住在
   `shared/module.py`，與前端的 `shared/module.ts` 對稱。
3. 跨 module 只能引用對方的 public entry：前端 `public.server.ts`／`public.client.ts`，後端 `public.py`。
4. **組裝層（前端 `app`／`config`、後端 `app`）也一樣**：只能引用 module 的 public entry 或 `manifest`，不可指進模組內部。組裝層不是特權層，它只是另一個使用者。
5. `manifest` 必須能在組裝階段安全載入。前端 manifest 不得引用 React、`server-only`、DOM 或瀏覽器 API。
6. 前端 client 檔不可引用 `.server.ts`／`.server.tsx`；唯一例外是含有 `"use server"` 的 Server Action。
7. 前端 module 內部一律用**相對路徑**（`./ui/ItemsView`），`@/` 只用來跨層。
   同一個模組時而 `./x` 時而 `@/modules/me/x`，會讓「這是自己的東西還是別人的」要讀到路徑尾才知道。
8. 前端 UI kit 只有 `@/shared/ui` 一個入口，不可指進 `shared/ui/` 的子路徑
   （`internals.ts` 與 `styles/**` 是實作細節）。唯一例外是 `app/layout.tsx` 載入的全域樣式表
   `shared/ui/styles/message-page.css` —— `global-error.tsx` 在 root layout 之外渲染，拿不到 CSS module。
9. 後端不得出現 `api`／`core`／`framework`／`repositories`／`services` 這類**水平分層**的
   頂層套件。功能是垂直切分的，開了水平層就會開始有「所有 service 放一起」的東西。

`npm run check:architecture` 以 TypeScript compiler API 檢查前端（規則 1–8）；後端
`tests/test_architecture.py` 以 Python AST 檢查兩邊共通的那幾條，外加規則 9。
兩者都包含在日常檢查中。

規則 9 之外，wire contract（REST 路徑、cookie 名稱、WS 事件、資料表名稱）
沒有獨立的檢查器 —— 它們靠 `make gen-types` 的型別產生流程與各自的測試守著，
改動時要自己確認影響面，見 [`../contracts/README.md`](../contracts/README.md)。

兩邊的檢查都涵蓋**所有**指向其他檔案的寫法，不只 `import`：

- 前端另外收 `export … from`（re-export）與動態 `import()`。每個 public entry 用的都是 re-export，漏掉它等於規則在最關鍵的接縫上失效。
- 後端另外把相對 import 解析成絕對名稱後再檢查。`from ..users.model import X` 是不折不扣的跨模組深入引用，只是寫法不同。

## 程式放置判斷

| 問題 | 放置位置 |
|---|---|
| 是 Next.js 的 `page`、`layout`、`loading`、`error` 嗎？ | `apps/web/app`，只做接線（分級規則見「Frontend module 介面」） |
| 是前端模組啟用、導覽、路由、導覽圖示或 WS handler 組裝嗎？ | `apps/web/config` |
| 是全站設計 token 或主題色票嗎？ | `apps/web/app/tokens`（原始值與語意）、`apps/web/app/themes`（各主題的 `--color-*`），規則見 [`design-system.md`](design-system.md) |
| 是單一業務功能的 action、能力、型別或資料載入嗎？ | `apps/web/modules/<name>` 的模組根 |
| 是單一業務功能的畫面嗎？（元件、只服務這些元件的 hook、該模組的 CSS module） | `apps/web/modules/<name>/ui` |
| 是至少兩個功能使用、且不含業務知識的 UI／API／session 能力嗎？ | `apps/web/shared` |
| 是 FastAPI server、環境設定、module registry 或 Permission enum 嗎？ | `apps/api/app` |
| 是單一業務功能的 router、schema、service、資料表 model 或權限 metadata 嗎？ | `apps/api/modules/<name>` |
| 是 domain-neutral 的 auth、db、http 或 time 能力嗎？ | `apps/api/shared` |

少量重複不等於 shared。沒有第二個實際使用者、或仍含某個 domain 規則時，先留在 module。

## Frontend module 介面

每個模組提供 `manifest.ts`，並依 runtime 提供 public entry：

這棵樹是**介面的形狀**，不是任何一個模組的實際清單 —— 每一列都標了哪個模組是它的
現成例子：

<!-- check-docs: tree - -->
```text
modules/<name>/
├── manifest.ts          # 必備。edge-safe 路由與導覽 metadata
├── public.server.ts     # 有 Server Component／Server Action 才需要
├── public.client.ts     # 有 client 端能力（WS handler、瀏覽器 API…）才需要
├── i18n.ts              # 必備。這個模組自己的中英兩份字串，沒有全站字典
├── capabilities.ts      # 選配。這個模組自己的 getRoleCapabilities 等能力判斷
├── actions.ts           # 選配。"use server" 的寫入動作
├── constants.ts         # 選配。要綁編譯期聯集的表（見 PERMISSION_ACTION_LABELS）
├── page.server.tsx      # 選配。模組主頁；其餘頁面是 <name>-page.server.tsx
├── realtime.ts          # 選配。這個模組的 WS 事件處理（現成例子：items）
├── types.ts             # 選配。畫面專屬型別（entity 從 shared/api/entities 來）
└── ui/                  # 有畫面就有：元件、只服務這些元件的 hook、該模組的 CSS module
```

**必備的是 `manifest.ts`、`i18n.ts` 與至少一個 public entry**（`check:architecture` 在守），
其餘按模組實際需要出現（`push` 沒有頁面所以沒有 `public.server.ts`；`settings` 不需要權限
判斷所以沒有 `capabilities.ts`）。這也不是封閉清單 —— 模組根可以有其他放資料與規則的檔案，
`auth` 就另有 `validation.ts` 與 `bootstrap.server.ts`。
**受約束的是分層，不是檔名**：資料與規則在模組根，畫面在 `ui/`。

畫面全部放 `ui/`，不要再往下開 `components/`、`hooks/`、`utils/`（`check:architecture`
會擋，實作是 `check-boundaries.mjs` 的 `collectLayoutErrors`）：
一個模組通常只有十幾個檔案，多分一層要付的是「每次找東西都得先猜它被歸到哪一類」。
一個模組有多個頁面時也一樣（見 `modules/auth`：`login-page.server.tsx` 與
`signup-page.server.tsx` 並排在模組根，表單元件與它們的 hook 並排在 `ui/`）。

- 模組根放**資料與規則**：載入、寫入、權限、型別、常數。
- `ui/` 放**畫面**：元件、只服務這些元件的 hook、該模組的 CSS module。
- `page.server.tsx` 只做「取資料 + 權限檢查 + 交給 `ui/<Name>View`」，不掛 className。
- 模組內部一律相對路徑（`./ui/RolesView`、`../types`）。
- 測試不在模組裡，在 `tests/modules/<name>/`（與後端同一套，見上方對照表）。

public entry 的形狀是固定的，一個 module 每種 runtime 只有一個檔（`public.server.ts`／`public.client.ts`），**一律具名轉出**：

```ts
// modules/roles/public.server.ts —— 一個模組有兩個頁面也不必再開第二個 entry
export { default as RolesPage, generateMetadata as generateRolesMetadata } from "./page.server"
export type { RolesPageProps } from "./page.server"
export { default as RoleEditPage, generateMetadata as generateRoleEditMetadata } from "./edit-page.server"
export type { RoleEditPageProps } from "./edit-page.server"
```

props 型別要一起轉出：route adapter 靠它接住 Next 傳進來的 props 再原封不動往下傳，
`searchParams` 的形狀就不必在模組與 adapter 各寫一次。

Next.js route adapter 是薄 wrapper，只做接線（寫法見
[`extending.md`](extending.md#新增前端頁面) 第 4 步）。

**Next 只讀 route 檔的 export，模組裡的不會自己跟過來**，而且漏掉一律沒有錯誤訊息 ——
漏掉 `metadata` 時，根 layout 的 `title.template` 會讓那一頁靜靜退回預設標題；漏掉
`revalidate` 之類的 route segment config 則是設定安靜地不生效。要逐一手動接上的完整清單：

`metadata`、`generateMetadata`、`viewport`、`generateViewport`、`generateStaticParams`、
`dynamic`、`dynamicParams`、`revalidate`、`fetchCache`、`runtime`、`preferredRegion`、
`maxDuration`、`experimental_ppr`。

`tests/app/route-adapters.test.ts` 守這件事：它用 TypeScript compiler API 比對
「頁面模組宣告了什麼」與「adapter 轉出了什麼」，並檢查 adapter 真的是薄的。
**認不出形狀的 route 檔一律當作失敗**，就地宣告頁面的例外要列進該檔的 `IN_PLACE_PAGES`
（目前只有首頁）—— 否則改寫法會讓整組檢查靜靜變成空轉。

不要改用 Next 產生的全域 `PageProps<"/x">`：它的 `searchParams` 是
`Promise<Record<string, string | string[] | undefined>>`，與模組宣告的窄型別不相容。
Next 的 page 驗證器只約束 `params`，其餘是 `& any`，所以窄型別維持現狀即可。

### `app/` 各種檔案的分級規則

「薄」的標準不是每種檔案都一樣 —— Next 規定的幾種檔案裡，只有 `page.tsx` 有模組可以委派：

| 檔案 | 允許的內容 |
|---|---|
| `page.tsx` | 只有 import、Next 特有 export 的轉接、一個回傳單一 JSX 的預設輸出。由測試強制 |
| `layout.tsx` | 可以有 session 讀取、`redirect()`、route group 層級的權限粗篩、組裝殼層元件。**不可有業務規則** —— 判斷用的函式一律來自 `shared/` 或模組的 public entry |
| `error.tsx`／`global-error.tsx`／`not-found.tsx`／`loading.tsx` | 組裝 `shared/ui` 的 `MessagePage`／`RouteLoading` 並填入文案 |
| `route.ts` | 不依賴任何模組、session 或後端的常數回應。要碰資料就表示它其實是後端的事，該加在 `apps/api` |

`app/healthz/route.ts` 是目前唯一一支 `route.ts`：Docker healthcheck 的探活端點，
只回一個常數 `ok`。它刻意什麼都不碰 —— 探活要回答的是「Next.js 伺服器還在回應嗎」，
探真實頁面會連帶 server-render 並打後端，等於每 10 秒多一次 API + 資料庫查詢，
也讓 web 的健康狀態跟著 api 一起紅（而 api 自己已經有 healthcheck）。
它同時列在 `proxy.ts` 的 matcher 排除清單裡。

`app/(protected)/page.tsx`（首頁）是唯一就地宣告頁面的 route 檔：它只有一段歡迎訊息，
為它開一個模組要付的維護成本高過收益。這是**刻意的例外**，且必須列在
`route-adapters.test.ts` 的 `IN_PLACE_PAGES` 裡才算數。

`config/routes.ts` 的 `ENABLED_MODULES` 是唯一的模組啟用清單：受保護路由陣列、`ProtectedRoutePath` 與 `NavIconKey` 全部從它推導，新增模組只加一行。`config/realtime/handlers.ts` 聚合 WS 事件 handler。

`config/shell/nav-icons.ts` 的 `NAV_ICONS` 是**第二個組裝點**：manifest 只能帶 `navIcon` 字串
（它要保持 edge-safe，不能把 React 元件帶進 middleware 會載入的 `routes.ts`），實際圖示在那裡對應。
有導覽的模組兩處都要加，漏掉會編譯失敗（型別是 `Record<NavIconKey, LucideIcon>`）。

### shared/ui 的公開面

UI kit 只從 `@/shared/ui` 匯出，子路徑一律不可引用。版面樣板在檔案裡是 default export，
barrel 一律轉成具名 —— 呼叫端只要記住一個路徑與一組名字。

需要 UI kit 的某個 class 時，**不要**改成 import `shared/ui/styles/*`，而是在 kit 裡多包一個元件
（`TableRow` 就是這樣來的：它只為了那一個把表格列轉成卡片的 class 而存在）。
樣式一旦外流，UI kit 就再也不能安全調整內部結構。

同理，**不要把帶 `server-only` 的模組放進 `shared/ui`**：這個 barrel 同時被 Server Component
與 client component 引用，只要有一個檔案帶了 `server-only`，所有 client 端的引用都會在建置時炸掉。
kit 內部檔案彼此引用時走相對路徑而不是 `@/shared/ui`，避免 barrel 自我循環。

### `"use client"` 只加在真的需要的檔案

kit 裡的檔案分成兩類，加不加指示詞是有判準的：

| 檔案 | 有 `"use client"` 嗎 | 為什麼 |
|---|---|---|
| `primitives.tsx`、`patterns/PageHeader`、`ListTableCard`、`StatusBadge`、`TableRow`、`feedback/MessagePage`、`feedback/ErrorState` | **沒有** | 沒有 state／effect／瀏覽器 API，也不讀 context。`Button` 只是把 `onClick` 往下傳，接住 handler 的是呼叫端 |
| `forms.tsx`、`dialogs.tsx`、`notifications.tsx`、`pagination.tsx`、`patterns/ActionMenu`、`FilterDialog`、`FormPageShell`、`ListPageHeader`、`feedback/RouteLoading`、`hooks/*` | 有 | 真的用到 `useState`／`useEffect`／`usePathname`／`useId`，或讀 i18n 的 `useT`（context 只有 client 讀得到） |

沒有指示詞的元件**兩邊都能用**：被 Server Component 引用就在伺服器算完，被 client
component 引用才進 client bundle。反過來，在版面元件上加 `"use client"` 會讓它們無條件
進 client bundle，也會逼得 Server Component 為了留在伺服器而自己手刻 markup。

**要加 state 或事件時請另開檔案**，不要在既有的版面檔上補指示詞 —— 那會一次把同檔案裡
所有元件都拖進 client。

### 版面規則住在 CSS，不寫進 style 屬性

`Flex` 的 `gap`／`align`／`justify` 這類 prop 不會變成 inline style，而是換算成
`--flex-*` 自訂屬性，實際規則寫在 `shared/ui/styles/primitives.module.css` 的 `:where(.flex)` 裡。
這樣換到兩件事：可以對版面寫 media query，以及呼叫端傳進來的 `className` 真的蓋得過預設
（inline style 的優先權高於任何 class，覆寫會靜靜失效）。

因此有兩條約束：

- **沒帶的 prop 不可以吐出值**，否則預設值會蓋掉呼叫端 class 設的同名屬性。
  `tests/shared/ui/ui.test.tsx` 的「Flex 的版面契約」在守這件事。
- 間距一律用 `spacing()` 換算成 `var(--space-n)`，刻度的單一事實來源在 CSS 那一側
  （見 [`design-system.md`](design-system.md)）；不要在元件裡算出 px。

## Backend module 介面

<!-- check-docs: tree apps/api/modules/roles -->
```text
modules/roles/
├── manifest.py          # 必備。routers、tables、permission metadata、身分來源
├── public.py            # 其他 module 唯一可引用的介面
├── router.py
├── schema.py
├── service.py
├── model.py             # RoleTable；`__tablename__` 保持不變
└── permissions.py
```

必備的同樣只有 `manifest.py`：`permissions` 模組只有 router 與 schema，`realtime` 沒有資料表
也沒有權限。測試放在 `tests/modules/<name>/`，與 `modules/<name>/` 同構 —— 整包刪除一個模組時，
測試在同一個路徑下跟著刪，不必回頭翻另一棵樹。

`app.registry.ENABLED_MODULES` 是唯一啟用清單。啟動時會拒絕重複的 module name、router prefix、model class 或 `__tablename__`；`create_app(modules=...)` 可在測試中替換啟用集合。

### 組裝層不認識任何具名 module

`app/` 只 import 各模組的 `manifest`，不 import 任何模組的實作。需要某個模組提供能力時，
走 manifest 上的欄位，而不是在 `server.py` 裡直接 import：

- `configure`：模組要讀環境設定時的初始化 hook（見 `modules/push`）。
- `current_user_resolver`：`shared/auth` 需要一個「以 username 取得使用者」的函式，
  但 shared 不認識 domain。由擁有使用者資料的模組（`users`）從 manifest 提供，
  `create_app()` 掛到 `app.state`。整個 app 至多一個模組提供，第二個會在組裝時 raise。

少了這條，`server.py` 會直接 `from modules.users.public import UserTable` ——
規則上合法（走的是 public entry），但 `users` 就事實上不可替換、也不可停用了。

### docstring 會外流到公開 API 文件

FastAPI 會把以下三種 docstring 放進 OpenAPI 的 `description`：

- route function 的 docstring
- 被某個端點實際使用的 pydantic model（`schema.py` 的 `Request` / `Response` 內部類別）
- 進到 schema 的 enum（例如 `WsEventType`）

它們會進到 OpenAPI schema，因此會被 `make gen-types` 複製進
`apps/web/shared/api/generated/schema.d.ts`，也會出現在 FastAPI 的 Swagger UI
（`/docs`，預設沒有經 nginx 對外，需要直接連到 api 容器才看得到）。也就是說，
**寫在這三個位置的內容是對 API 呼叫者說話的**，不是給維護者看的。

因此：

- 這三處只寫呼叫端需要知道的事 —— 這個端點做什麼、回傳什麼、什麼時候會失敗。
- 內部設計說明、型別產生策略、「為什麼不用另一種做法」，寫在**模組層 docstring** 或
  一般註解裡（那些不會進 OpenAPI）。範例見 `modules/realtime/schema.py` 開頭。
- 改動這三處之後要跑 `make gen-types`，否則 CI 的 `api-types-up-to-date` job 會紅燈。

想確認某段文字有沒有外流，跑完 `make gen-types` 後直接查產出：

```bash
grep -n "你寫的那句話" apps/web/shared/api/generated/schema.d.ts
```

`Permission` enum 留在 `app/permissions.py`，確保 Python 與 OpenAPI 的靜態型別穩定。每個功能只在自己的 `permissions.py` 提供 label、dependencies 與 assignable metadata。這兩件事分開處理：

- `app.registry` 在載入時呼叫 `validate_permission_coverage()`，確認完整啟用清單剛好覆蓋整個 enum（多了一個 enum 成員卻沒人提供 metadata，權限會存在但永遠指派不出去）。這是純驗證，不安裝任何狀態。
- `create_app()` 再以**它實際拿到的** modules 呼叫 `build_permission_catalog()`，把結果掛到
  `app.state.permission_catalog`（resolver 一併掛到 `app.state.permission_resolver`）。
  所以停用一個 module 之後，`GET /permissions/` 不會再提供它的權限。

目錄是**每個 app 一份的值**，不是行程層級的全域 —— 需要它的人從 `request.app.state` 取
（`modules/permissions/router.py` 與 `modules/users/router.py` 都是這樣做）。
改成全域的話，同一個行程裡的第二次 `create_app()` 會靜靜換掉第一個 app 的目錄與相依展開，
而症狀取決於呼叫順序。這與 `current_user_resolver` 是同一套注入方式，理由也相同。

### 三份刻意中央化的清單

`app/permissions.py` 的 `Permission`、`modules/realtime/schema.py` 的 `WsEventType`
與 `shared/http/errors.py` 的 `Language` 是全專案
**僅有的三處「新增功能要去改共用檔案」**。三者都是為了同一件事：它們要進 OpenAPI 成為靜態字串聯集，
前端才能拿到編譯期保護（權限打錯字、後端加了事件前端沒跟上，都會是 `tsc` 失敗而不是 runtime 靜默失效）。
改成「由各模組動態貢獻」會把這層保護換掉，所以刻意不改。

代價要知道：`items` 新增一個 WS 事件時，要去 `modules/realtime/schema.py` 加 enum 成員 ——
這是唯一允許的跨模組寫入，移除模組時也要記得一起刪。除此之外，權限的 label／dependencies
仍然完全歸各模組自己的 `permissions.py` 所有。

## 新增 module

操作步驟見 [`extending.md`](extending.md)。這裡只列會影響邊界的四條約束：

1. 前後端模組**同名**（例如 `push` 對 `push`）；只有單邊存在的模組不強求對應（對照見開頭那張表）。
2. 跨模組需求先設計**最小的** public entry；禁止 deep import，組裝層也一樣。
3. entity 型別預設留在模組自己的 `types.ts`（從 generated schema 衍生）；
   出現第二個模組的使用者時才搬進 `shared/api/entities.ts`。
4. 前後端測試都放 `tests/modules/<name>/`，與 `modules/<name>/` 同構。

## 移除 module

一個模組要能整包刪掉，且**不必修改 `shared/`**。中央 registry、`Permission` enum 與
Next route adapter 是刻意保留的必要組裝點，只需拿掉該模組的那幾行。唯一會動到別的模組的
情況是該模組有註冊 WS 事件 —— 那要去 `modules/realtime/schema.py` 刪掉自己的 enum 成員，
理由見上一節。

**兩組模組之間有依賴，刪之前要知道**：前端 `users` 用 `roles` 的公開面渲染角色名稱
（`capabilities.ts` 與 `ui/` 底下三個檔），`settings` 用 `push` 的公開面渲染推播開關。
`roles` 與 `users` 都是核心，實務上不會刪；`push` 的那一組列在下面的剝除清單裡。

以 `items` 為例 —— 它存在的唯一目的是當範例，多數專案的第一件事就是刪掉它：

<!-- check-docs: ignore-start -->
<!-- 這一節的主題就是「這些檔案不再存在」，刪完之後它必然指向不存在的路徑。 -->

**後端**

| 位置 | 動作 |
|---|---|
| `apps/api/modules/items/` | 整個目錄 |
| `apps/api/tests/modules/items/` | 整個目錄（測試與 module 同構） |
| `apps/api/tests/modules/test_detail_contracts.py` | `ItemDetail`／`ItemTable` 的 import、`_CLEANUP_ORDER` 裡的項目與 `test_item_detail_matches_create_and_find`。**這個檔案不刪**，其他模組還在用它 —— 但它的 import 在 module 層級，漏了會讓整個後端測試在 collection 階段就 ImportError |
| `apps/api/app/registry.py` | `ITEMS_MODULE` 的 import 與 `ENABLED_MODULES` 項目 |
| `apps/api/app/permissions.py` | `ITEM_*` enum 成員 |
| `apps/api/modules/realtime/schema.py` | `WsEventType.ITEM_CREATED` |

**前端**

| 位置 | 動作 |
|---|---|
| `apps/web/modules/items/` | 整個目錄（含 `ui/` 底下的元件與 CSS module） |
| `apps/web/tests/modules/items/` | 整個目錄（測試與 module 同構） |
| `apps/web/app/(protected)/items/` | Next.js 薄路由 |
| `config/routes.ts` | `ITEMS_MODULE` 的 import 與 `ENABLED_MODULES` 項目（route／icon 的型別聯集會自動縮小） |
| `config/realtime/handlers.ts` | items realtime handler 的 import 與展開 |
| `config/shell/nav-icons.ts` | `NAV_ICONS` 的 items 條目 |
| `web/modules/roles/constants.ts` | `PERMISSION_ACTION_LABELS` 的五個 `items:*` 標籤 |

**e2e**

| 位置 | 動作 |
|---|---|
| `e2e/tests/items.spec.ts` | 整個檔案。**漏了的症狀很糟**：刪完 items 之後 e2e job 會紅，而錯誤是「找不到新增項目按鈕」—— 完全指不回這裡。`e2e/tests/bootstrap.setup.ts` 與 `proxy.spec.ts` 不刪，它們與 items 無關 |

**收尾**

```bash
rm -rf apps/web/.next   # 清掉 Next.js 為已刪除路由產生的舊型別，否則 tsc 會報找不到模組
make gen-types
make check
make check-docs         # 列出 docs/ 裡還拿 items 當範例的每一行，刪掉即可
```

`WsEventType` 保留一個 domain-neutral 的 `SYSTEM_ANNOUNCEMENT`，所以型別聯集不會變成空的，
WS 機制在 items 刪除後仍然可用。

### 剝除基礎設施模組

`items` 是範例，沒有人依賴它，所以上面三步就夠了。`realtime` 與 `push` 不一樣 ——
它們是**有反向依賴的基礎設施**，剝除時會動到組裝層與其他模組。不需要即時通知或推播的專案
應該整包移除，但要照下面的清單走。

**移除 `realtime`（WebSocket）**

| 位置 | 動作 |
|---|---|
| `api/modules/realtime/`、`tests/modules/realtime/` | 整包刪除 |
| `api/app/registry.py` | 移除 `REALTIME_MODULE` |
| `api/modules/items/service.py` | 刪掉 `create_item` 裡送 WS 事件的整段（連同 `modules.realtime.public` 的 import）。若 items 也要刪就不用管 |
| `web/config/realtime/` | 整包刪除（`WSManager.tsx` 與 `handlers.ts`） |
| `web/app/(protected)/layout.tsx` | 移除 `<WSManager />` 與它的 import |
| `web/shared/realtime/`、`web/tests/shared/realtime/` | 整包刪除 |
| `web/shared/api/entities.ts` | 移除 `WsEventType`、`WsEvent` 兩個型別與其上方的說明 |
| `web/modules/*/realtime.ts` | 各模組自己的事件處理 |

`shared/auth/` 底下只有 **docstring** 提到 realtime（`dependency.py`、`tokens.py` 說明 ws ticket
與 HTTP 共用同一套 auth\_version 判斷），沒有程式相依 —— 順手把那兩段註解修掉即可，
不需要動程式。ws ticket 的簽發函式在 `shared/auth/tokens.py`，若確定不會再用可一併移除。

**移除 `push`（Web Push）**

| 位置 | 動作 |
|---|---|
| `api/modules/push/`、`api/tests/modules/push/` | 整包刪除 |
| `api/app/registry.py` | 移除 `PUSH_MODULE` |
| `api/app/permissions.py` | 移除 `PUSH_SEND` enum 成員 |
| `api/pyproject.toml`、`api/uv.lock` | 移除 `pywebpush`，在 `apps/api` 跑 `uv lock` 更新 lock |
| `.env`、`.env.example`、`scripts/init.sh` | 移除 `VAPID_*` 三個變數與產生金鑰的程式 |
| `scripts/check-env.sh` | 從 `SECRETS` 移除 VAPID 金鑰 |
| `infra/docker/docker-compose.yml` | 移除 api 與 web 的 `VAPID_*` 環境變數（`.dev.yml` 只有一句提到它們的註解） |
| `web/modules/push/`、`web/tests/modules/push/` | 整包刪除 |
| `web/config/routes.ts` | 移除 `PUSH_MODULE` |
| `web/app/(protected)/layout.tsx` | 移除 `<PushNotificationManager />` |
| `web/Dockerfile` | 沒有 build arg 要刪（VAPID 走執行期注入），只要修掉 builder stage 那段提到它的註解 |
| `apps/web/public/sw.js` | service worker，只服務推播 |
| `web/knip.ts` | 移除 `public/sw.js` entry |
| `web/vitest.config.ts` | 從 coverage include 移除 `modules/push/encoding.ts` |
| `web/modules/roles/constants.ts` | 移除 `PERMISSION_ACTION_LABELS` 的 `"push:send"` 一行 |
| `web/shared/api/entities.ts` | 註解裡提到 `push:send`，順手修掉（沒有程式相依） |
| `web/modules/settings/ui/SettingsView.tsx` | 移除 `NotificationSettings` 的 import 與渲染 |
| `web/modules/settings/ui/NotificationSettings.tsx` | 整個檔案 |
| `web/modules/settings/i18n.ts` | `notificationSection`、`pushNotification`、`pushUnsupported`、`pushDenied` 四個 key（中英各一份） |
| `web/modules/settings/ui/settings.module.css` | `.toggle`、`.toggleInput`、`.toggleSlider` |
| `api/tests/test_i18n_text_usage.py` | 移除 `NotificationPayload` 的靜態規則 |
| `api/modules/realtime/manager.py` | 修掉 docstring 裡的 push 呼叫端說明 |
| `.github/workflows/ci.yml` | **兩個 job 各有一份驗證用的假 `.env`**：`deploy-config` 與 `e2e`，各移除 `VAPID_*` 三行；再修掉 `publish` 那段提到它的註解 |
| `README.md`、`TEMPLATE.md`、`docs/` | 移除推播功能與用法；最後刪掉本節 |

`settings` 本身**不用刪**：`SettingsView` 還有 `LanguageSettings`（語系切換），
拿掉推播開關之後仍是一個有內容的頁面。這是**基礎設施模組**唯一一組跨模組的畫面依賴，
所以它出現在 `push` 的清單裡，而不是 `settings` 自己的問題。

設定頁的字典那一列**沒有檢查器在守**：多餘的 key 兩種語言都齊全，所以型別是對的，
漏刪不會紅燈，只會留下死碼。CSS 那一列有 —— 沒人引用的 class 由
`npm run check:tokens` 擋（knip 只看 `.ts`／`.tsx`，見 [`design-system.md`](design-system.md)）。

**剝除完的收尾順序不能顛倒**：先 `make gen-types` 再 `make check`。

```bash
rm -rf apps/web/.next   # 不清的話 tsc 會抱怨找不到已刪除路由的型別
make gen-types               # 權限聯集與端點型別會跟著縮小
make check
make check-env               # VAPID 的清單、產生腳本與 compose 必須一起縮小
make check-docs              # 列出文件裡還指著已刪模組的每一行
```

`make gen-types` 這一步不是形式：後端刪掉 `PUSH_SEND` 之後，`Permission` 聯集會少一個成員，
`modules/roles/constants.ts` 那份 `satisfies Record<PermissionValue, string>` 的窮盡標籤表
就會**編譯失敗**並指名多出來的那一個。上面表格裡「還要改哪些檔案」就是這樣被找出來的 ——
不先重產型別，只會看到一切正常，直到下次有人跑 CI。

**編譯過了只算程式碼剝乾淨。** 文件不會編譯，所以最後那一步是 `make check-docs`：
`docs/extending.md` 拿 `items` 當範例的地方會被逐行列出來，刪掉那幾個指路即可
（`items` 沒了，那些「複製這個」的說明本來就沒有對象了）。不跑的話，
你的專案會留著一份指向不存在目錄的教學文件 —— 而那是下一個人最先讀的東西。

<!-- check-docs: ignore-end -->
