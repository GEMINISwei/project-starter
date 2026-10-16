# 模組化架構

前後端用同一套三層結構，依賴只能往右：

```text
app（組裝層） → modules（垂直功能） → shared（平台能力）
```

- `app`：框架入口與組裝點，只決定啟用哪些模組、怎麼掛載。
- `modules`：一個完整的功能，包含它的資料、規則、API／畫面。
- `shared`：不認識任何業務名稱、多個模組共用的能力。

這份文件只講**規則與介面**，操作步驟見 [`extending.md`](extending.md)。

## 目錄結構

```text
<project>/
├── apps/
│   ├── api/                  # FastAPI
│   │   ├── main.py           # 進入點（uvicorn）
│   │   ├── app/              # 組裝層：config、server、registry、Permission enum（只放專案自己的）
│   │   ├── modules/          # users、roles、languages
│   │   ├── shared/           # auth、db、http、time + module.py（manifest 契約）、platform.py（接線）
│   │   ├── tests/            # 與原始碼同構
│   │   ├── scripts/          # db.py（資料庫 CLI）、export_openapi.py
│   │   └── migrations/       # Alembic
│   │
│   └── web/                  # Next.js
│       ├── app/              # Next.js 路由檔（只做接線）+ theme.css（專案的外觀覆寫）
│       ├── config/           # 組裝層：啟用模組、路由、導覽圖示、外殼字串
│       ├── modules/          # auth、users、roles、settings
│       ├── shared/           # api、session、access、pagination、i18n、runtime、ui
│       │                     # + module.ts（manifest 契約）
│       ├── proxy.ts          # 路由保護（Next 只認根目錄，不能搬）
│       ├── tests/            # 與原始碼同構
│       └── .dependency-cruiser.cjs   # 前端依賴邊界
│
├── contracts/openapi.json    # 後端產生、進版控，前端型別的唯一來源
├── infra/                    # docker compose、nginx 模板（共用片段在 nginx/snippets/）
├── scripts/                  # make 指令的實作
└── docs/
```

兩個 app 都**沒有 `src/`**：後端 import root 是 `apps/api/`（`from modules.users.public import …`），
前端 `@/` 指向 `apps/web/`。**新增一層原始碼目錄時，要同步加進兩個檢查工具的掃描範圍**
（`apps/web/package.json` 的 `check:architecture`、`apps/api/pyproject.toml` 的 `root_packages`），
漏掉不會報錯，只是那一層不再受邊界規則管。

## 前後端對照

| 概念 | 後端 | 前端 |
|---|---|---|
| 組裝層 | `app/` | `config/`（前端的 `app/` 是 Next.js 規定的路由目錄，在依賴規則上與 `config/` 同一層） |
| 垂直功能 | `modules/` | `modules/` |
| 平台能力 | `shared/` | `shared/` |
| 測試 | `tests/`，與原始碼同構 | 同左 |

前後端都有的模組**一律同名**（`users`、`roles`）。只有單邊的：

| 後端 | 前端 | 為什麼 |
|---|---|---|
| `languages` | 無 | 只為了把 `Language` enum 送進 OpenAPI |
| 無 | `auth`、`settings` | 純畫面，呼叫的是 `users` 與 `languages` 的端點 |

## 強制依賴規則

1. `shared` 不可引用 `modules` 或組裝層。
2. module 可引用 `shared`，**不可引用組裝層**；需要組裝層決定的東西時，由參數或 `app.state`
   傳進來。唯一例外是後端的 `app.permissions`（見〈[兩份刻意中央化的清單](#兩份刻意中央化的清單)〉）。
3. 跨 module 只能引用對方的 **public entry**：前端 `public.server.ts`／`public.client.ts`，後端 `public.py`。
4. **組裝層也一樣**，只能引用 module 的 public entry 或 `manifest`，沒有特權。
5. `manifest` 要能在組裝階段安全載入：前端 manifest 不得引用 React、`server-only`、DOM 或瀏覽器 API。
6. 前端 client 檔不可引用 `.server.ts(x)`，`"use server"` 的 Server Action 除外。
7. 前端 module 內部一律**相對路徑**，`@/` 只用來跨層。
8. 前端 UI kit 只有 `@/shared/ui` 一個入口，不可指進子路徑。唯一例外是文件根（`app/layout.tsx`、
   `app/global-error.tsx`）載入的全域樣式表 `shared/ui/styles/{tokens,base,message-page}.css`。
9. 後端不得有 `api`／`core`／`services`／`repositories` 這類**水平分層**的頂層套件。

違反就紅燈（`make check`），各條由現成工具執行，都涵蓋 re-export、動態 `import()` 與相對 import：

| 規則 | 後端 | 前端 |
|---|---|---|
| 1–4、8 依賴方向 | import-linter（`pyproject.toml`） | dependency-cruiser（`.dependency-cruiser.cjs`） |
| 5 manifest edge-safe | — | dependency-cruiser（含間接依賴）+ ESLint |
| 6 client 不引 server | — | Next.js build（`.server` 檔一律 `import "server-only"`） |
| 7 模組內部相對路徑 | — | ESLint |
| 9 不准水平分層 | `tests/test_architecture.py` | — |

## 程式放在哪

| 它是什麼 | 放哪裡 |
|---|---|
| Next.js 的 `page`／`layout`／`loading`／`error` | `apps/web/app/`，只做接線 |
| 模組啟用、路由、導覽圖示 | `apps/web/config/` |
| 設計變數的名字與預設值 | `apps/web/shared/ui/styles/tokens.css` |
| 這個專案的外觀（覆寫設計變數） | `apps/web/app/theme.css` |
| 單一功能的資料載入、action、權限判斷、型別 | `apps/web/modules/<name>/` |
| 單一功能的畫面（元件、只服務畫面的 hook、CSS module） | `apps/web/modules/<name>/ui/` |
| 至少兩個功能用到、不含業務知識的能力 | `apps/web/shared/`、`apps/api/shared/` |
| 環境設定、啟用清單、Permission enum 的成員 | `apps/api/app/` |
| 與業務無關的 FastAPI 接線（middleware、例外處理、lifespan） | `apps/api/shared/platform.py` |
| 單一功能的 router、schema、service、model、權限 metadata | `apps/api/modules/<name>/` |

**少量重複不等於 shared。** 還沒有第二個使用者、或含有某個業務規則時，先留在 module。

## Frontend module 介面

```text
modules/<name>/
├── manifest.ts          # 必備。edge-safe 的路由與導覽 metadata
├── i18n.ts              # 必備。這個模組自己的中英字串
├── public.server.ts     # 至少要有一個 public entry
├── public.client.ts
├── page.server.tsx      # 選配。其餘頁面命名為 <name>-page.server.tsx
├── actions.ts           # 選配。"use server" 的寫入動作
├── capabilities.ts      # 選配。畫面用的分支邏輯（要寫測試）
├── constants.ts、types.ts、validation.ts …
└── ui/                  # 畫面：元件、只服務畫面的 hook、CSS module
```

- **約束的是分層，不是檔名。** 模組根放資料與規則，`ui/` 放畫面；不要再開 `components/`、
  `hooks/`、`utils/`（檢查器會擋）。
- `page.server.tsx` 只做「取資料 + 權限檢查 + 交給 `ui/<Name>View`」。
- public entry **一律具名轉出**，props 型別也要轉出（route adapter 靠它往下傳）：

  ```ts
  // modules/roles/public.server.ts
  export { default as RolesPage, generateMetadata as generateRolesMetadata } from "./page.server"
  export type { RolesPageProps } from "./page.server"
  ```

### `app/` 的路由檔

畫面分成兩區，各有自己的外殼與導覽。使用者區是 route group（不出現在網址裡），管理區是真正的路徑段（網址一律在 `/admin/...` 底下）：

```text
app/
├── (public)/              # login、signup
└── (protected)/           # layout：登入檢查
    ├── (user)/            # 使用者區：首頁、個人設定　layout：使用者外殼
    └── admin/             # 管理區：使用者、角色管理　layout：權限檢查 + 管理外殼
```

路由放哪一區由 manifest 的 `group: "user" | "admin"` 決定，頁面檔要放在對應的 route group
或目錄底下，管理區路由的 `path` 要以 `/admin/` 開頭（`tests/config/routes.test.ts` 檢查）。
有管理權限的人在兩區之間有切換連結。

| 檔案 | 允許的內容 |
|---|---|
| `page.tsx` | 只有 import、Next 特有 export 的轉接、回傳單一 JSX（測試強制） |
| `layout.tsx` | session 讀取、`redirect()`、粗略的權限篩選、組裝外殼。**不可有業務規則** |
| `error`／`global-error`／`not-found`／`loading` | 用 `shared/ui` 的 `MessagePage`／`RouteLoading` 填文案 |

**`<main>` 地標由外框的擁有者提供**：`(protected)` 兩區是外殼（`config/shell/AreaLayout.tsx`），
頁面與模組不要再渲染 `<main>`（`tests/architecture.test.ts` 擋）；公開頁（登入、註冊）與整頁的
`MessagePage` 沒有外殼，自己提供。
| `route.ts` | 不依賴模組、session 或後端的常數回應（目前只有 `healthz`） |

**Next 只讀 route 檔自己的 export，模組裡的不會跟過來**，漏掉沒有錯誤訊息。要逐一接上的：
`metadata`、`generateMetadata`、`viewport`、`generateViewport`、`generateStaticParams`、`dynamic`、
`dynamicParams`、`revalidate`、`fetchCache`、`runtime`、`preferredRegion`、`maxDuration`、
`experimental_ppr`。
`tests/app/route-adapters.test.ts` 會比對兩邊；就地宣告頁面的例外列在 `IN_PLACE_PAGES`（只有首頁）。

前端有**兩個組裝點**：`config/routes.ts` 的 `ENABLED_MODULES`（路由、導覽、proxy 保護都從它推導）
與 `config/shell/nav-icons.ts` 的 `NAV_ICONS`（漏了會編譯失敗）。

### shared/ui

- 只從 `@/shared/ui` 匯出。需要 kit 的某個樣式時，在 kit 裡多包一個元件，不要讓 class 外流。
- **不要放帶 `server-only` 的東西**：client component 也會引用這個入口。
- **`"use client"` 只加在真的用到 state、effect、context 的檔案**；要加互動時另開檔案，不要在
  既有的版面檔補指示詞（會把同檔所有元件拖進 client bundle）。
- 間距用 `spacing()` 換成 `var(--space-n)`，不要在元件裡算 px；`Flex` 沒帶的 prop 不可輸出
  預設值，否則會蓋掉呼叫端的 class（`tests/shared/ui/ui.test.tsx` 守）。

## Backend module 介面

```text
modules/products/
├── manifest.py          # 必備。routers、tables、permissions
├── public.py            # 其他 module 唯一可引用的介面
├── router.py
├── schema.py
├── service.py
├── model.py
└── permissions.py       # 有引入權限時才有 (users、roles 沒有: 後台只開放給超級管理者)
```

- **service 長大了就依授權模型拆檔**，不要開 `services/` 子目錄。例：`modules/users/` 的
  `service.py`（管理者對任意使用者）、`account.py`（使用者對自己的帳號）、`bootstrap.py`
  （建立超級管理者），共用的錯誤在 `errors.py`。
- 與業務無關的能力（密碼雜湊、token、權限展開）用 `shared/auth/`，不要在模組裡再寫一份。
- `app/registry.py` 的 `ENABLED_MODULES` 是唯一啟用清單。重複的 module 名稱、router prefix、
  資料表名稱會在啟動時被拒絕（規則在 `shared/module.py`）。測試可用 `create_app(modules=...)`
  組出部分模組的 app。
- `app/server.py` 只呼叫 `shared/platform.py` 的 `create_platform_app()`，傳入環境設定、權限 enum
  與啟用的 modules。接線本身與業務無關，所以跟著 shared 走。
- **組裝層不 import 任何模組的實作**，只 import manifest。模組要提供能力給組裝層時走 manifest 的
  欄位（例如 `users` 用 `current_user_resolver` 提供身分來源），否則那個模組就不可替換了。
- 權限目錄是**每個 app 一份**（`app.state.permission_catalog`），依實際啟用的模組建立，不要改成
  全域變數。
- **docstring 會外流到 API 文件**：route function、端點用到的 pydantic model、進到 schema 的 enum，
  它們的 docstring 會進 OpenAPI 與前端型別檔。這三處只寫給呼叫端看的內容，內部設計說明寫在
  模組層 docstring 或一般註解（範例見 `modules/users/schema.py` 開頭）。

### 兩份刻意中央化的清單

`app/permissions.py` 的 `Permission` 與 `shared/http/errors.py` 的 `Language` 是**僅有的兩處**
「新增功能要改共用檔案」的地方。它們要進 OpenAPI 成為字串聯集，前端才拿得到編譯期保護
（權限打錯字是 `tsc` 失敗，而不是執行期靜默失效），所以不要改成由模組動態貢獻。

## 前後端契約

`contracts/openapi.json` 是後端對外的介面，也是前端型別的**唯一來源**：

```text
apps/api/modules/*/schema.py、app/permissions.py
        │  make gen-types
        ▼
contracts/openapi.json                         ← 契約本體
        │  make gen-types（openapi-typescript）
        ▼
apps/web/shared/api/generated/schema.d.ts      ← 前端型別
        │
        ▼
apps/web/shared/api/entities.ts                ← 平台 entity（Permission、Language、分頁形狀）
apps/web/modules/*/types.ts                    ← 業務 entity，以 Schema<"RoleInfo"> 命名
```

兩份產出都進版控，讓「後端改了對外介面」在 code review 的 diff 裡直接看得到；沒有重產時
CI 的 `check` job 會擋。什麼時候要跑 `make gen-types` 見 [`development.md`](development.md#指令)。
兩個檔案的路徑只定義在 `scripts/lib/common.sh` 的 `CONTRACT`、`WEB_SCHEMA`
（`make gen-types` 與 CI 用的 `make check contract` 都從那裡讀）。

## 新增與移除 module

新增的步驟見 [`extending.md`](extending.md#新增一個功能模組)。原則：前後端同名；public entry
從**最小**開始設計；業務 entity 型別一律在用到它的模組的 `types.ts` 以 `Schema<"…">` 命名，
不搬進 shared（理由見〈[shared 的可移植性](#shared-的可移植性)〉）。

**一個模組要能整包刪掉，而且不必改 `shared/`**：

| 位置 | 動作 |
|---|---|
| `apps/api/modules/<name>/`、`apps/api/tests/modules/<name>/` | 整包刪除 |
| `apps/api/app/registry.py`、`app/permissions.py` | 移除 manifest 與 enum 成員 |
| `apps/web/modules/<name>/`、`apps/web/tests/modules/<name>/`、`apps/web/app/(protected)/(<區>)/<path>/` | 整包刪除 |
| `apps/web/config/routes.ts`、`config/shell/nav-icons.ts` | 移除 manifest 與圖示 |

權限的標籤與分類跟著模組的 `permissions.py` 一起消失，角色畫面不必改。收尾**先 `make gen-types`
再 `make check`**，前端還在用的已刪除端點或權限才會變成編譯錯誤。另外清掉 `apps/web/.next`
（否則 `tsc` 會找已刪除路由的型別），帶環境變數的模組要把
[同步點](development.md#環境變數的同步點)一起縮小。

`users` 依賴 `roles` 的公開面（顯示角色名稱），這兩個是核心模組，實務上不會刪。

## shared 的可移植性

兩個 app 的 `shared/` 都承諾：**整包複製到另一個專案（沒有這裡的 `app/`、`modules/`、`config/`）
就能用**，連同 `tests/shared/`。所以 shared 除了不 import 業務程式，還要做到：

| 不能有的 | 改放哪裡 |
|---|---|
| 具體的業務端點（`/users/me`）或業務 entity（`UserInfo`） | 擁有它的模組；entity 在模組的 `types.ts` 以 `Schema<"…">` 命名 |
| 只定義在專案裡的設計變數 | `shared/ui/styles/tokens.css` 給預設值，專案在 `app/theme.css` 覆寫 |
| 讓 shared 能運作、卻寫在組裝層的接線 | `shared/platform.py`（`create_platform_app()`） |
| 依賴專案啟用清單的測試 | 後端 `tests/app/`、前端 `tests/` 根目錄或 `tests/modules/` |

前後端的 shared 是**一對**：前端假設後端的錯誤格式、`Accept-Language`、`X-Request-ID` 與 token
cookie 的協定，也假設 OpenAPI 裡一定有 `Permission` 與 `Language` 兩個 schema（新專案沿用
`modules/languages` 即可，或像 `apps/api/tests/shared/minimal_app.py` 自己帶進來）。
前端 shared 另外要求專案在 `LOGIN_PATH` 提供登入頁並認得 `?reason=`，約定寫在
`apps/web/shared/session/login-contract.ts`（這個模板由 `modules/auth` 提供）。

實際移植的步驟見 [`extending.md`](extending.md#把-shared-帶到另一個專案)。

`make check portable`（`make check` 與 CI 都會跑）實際把兩邊的 shared 複製到暫存目錄：後端跑
mypy 與 pytest；前端用**只有平台 schema** 的契約跑 `tsc` 與 vitest。shared 引用了任何業務
端點或 entity，就是編譯錯誤。

