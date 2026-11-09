# 模組化架構

前後端用同一套三層結構，依賴只能往右：

```text
app（組裝層） → modules（垂直功能） → shared（平台能力）
```

- `app`：框架入口與組裝點，只決定啟用哪些模組、怎麼掛載。
- `modules`：一個完整的功能，包含它的資料、規則、API／畫面。
- `shared`：多個模組共用的能力。

這份文件只講**規則與介面**，操作步驟見 [`extending/`](extending/README.md)。

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
├── e2e/                      # Playwright：整套系統的瀏覽器測試（make check e2e）
├── infra/                    # docker compose、nginx 模板（共用片段在 nginx/snippets/）
├── scripts/                  # make 指令的實作
└── docs/
```

兩個 app 都**沒有 `src/`**：後端 import root 是 `apps/api/`（`from modules.users.public import …`），前端 `@/` 指向
`apps/web/`。**新增一層原始碼目錄要加進掃描範圍**（`check:architecture`、`root_packages`），否則那層不受邊界規則管（架構測試擋）。

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
   `app/global-error.tsx`）載入的全域樣式表 `shared/ui/styles/{base,message-page}.css`。
   `tokens.css` 由 `app/theme.css` 以 `@import` 帶入，文件根只 import `theme.css`，順序才有保證
   （`tests/app/theme.test.ts` 擋）。
9. 後端不得有 `api`／`core`／`services`／`repositories` 這類**水平分層**的頂層套件。
10. 後端 `public.py` 只轉出能力（函式與它的回傳型別），**不轉出 ORM 類別或 `Table`**
    （見〈[模組之間的資料關聯](#模組之間的資料關聯)〉）。

違反就紅燈（CI 的 `lint`，本機可跑 `make check lint`），各條由現成工具執行，都涵蓋 re-export、動態 `import()` 與相對 import：

| 規則 | 後端 | 前端 |
|---|---|---|
| 1–4、8 依賴方向 | import-linter（`pyproject.toml`） | dependency-cruiser（`.dependency-cruiser.cjs`） |
| 5 manifest edge-safe | — | dependency-cruiser（含間接依賴）+ ESLint |
| 6 client 不引 server | — | Next.js build（`.server` 檔一律 `import "server-only"`） |
| 7 模組內部相對路徑 | — | ESLint |
| 9 不准水平分層 | `tests/test_architecture.py` | — |
| 10 public 不轉出資料表 | `tests/test_architecture.py` | — |

## 程式放在哪

| 它是什麼 | 放哪裡 |
|---|---|
| Next.js 的 `page`／`layout`／`loading`／`error` | `apps/web/app/`，只做接線 |
| 模組啟用、路由、導覽圖示 | `apps/web/config/` |
| 設計變數的名字與預設值 | `apps/web/shared/ui/styles/tokens.css` |
| 這個專案的外觀（覆寫設計變數） | `apps/web/app/theme.css` |
| 單一功能的資料載入、action、權限判斷、型別 | `apps/web/modules/<name>/` |
| 單一功能的畫面（元件、只服務畫面的 hook、CSS module） | `apps/web/modules/<name>/ui/` |
| 至少兩個功能用到的共用能力 | `apps/web/shared/`、`apps/api/shared/` |
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

- **約束分層，不約束檔名**：模組根放資料與規則，`ui/` 放畫面；不開 `components/`、`hooks/`、`utils/`（檢查器擋）。
- `page.server.tsx` 只做「取資料 + 權限檢查 + 交給 `ui/<Name>View`」。
- public entry **一律具名轉出**，props 型別也要轉出（route adapter 靠它往下傳）：

  ```ts
  // modules/roles/public.server.ts
  export { default as RolesPage, generateMetadata as generateRolesMetadata } from "./page.server"
  export type { RolesPageProps } from "./page.server"
  ```

### `app/` 的路由檔

兩區各有外殼與導覽：使用者區是 route group（不出現在網址），管理區是真正的路徑段（`/admin/...`）：

```text
app/
├── (public)/              # login
└── (protected)/           # layout：登入檢查
    ├── (user)/            # 使用者區：首頁、個人設定　layout：使用者外殼
    └── admin/             # 管理區：使用者、角色管理　layout：權限檢查 + 管理外殼
```

manifest 的 `group: "user" | "admin"` 決定區域，頁面檔放在對應的目錄，管理區的 `path` 以 `/admin/` 開頭
（`tests/config/routes.test.ts` 檢查）。有管理權限的人在兩區間有切換連結。

| 檔案 | 允許的內容 |
|---|---|
| `page.tsx` | 只有 import、Next 特有 export 的轉接、回傳單一 JSX（測試強制） |
| `layout.tsx` | session 讀取、`redirect()`、粗略的權限篩選、組裝外殼。**不可有業務規則** |
| `error`／`global-error`／`not-found`／`loading` | 用 `shared/ui` 的 `MessagePage`／`RouteLoading` 填文案。`global-error` 取代整個 root layout，要自己再載入 layout 的那組樣式表 |
| `route.ts` | 不依賴模組、session 或後端的常數回應（目前只有 `healthz`） |

**`<main>` 由外框提供**：`(protected)` 兩區由外殼（`config/shell/AreaLayout.tsx`）提供，頁面與模組不再渲染
（`tests/architecture.test.ts` 擋）；公開頁與整頁的 `MessagePage` 沒有外殼，自己提供。

**Next 只讀 route 檔自己的 export，模組裡的不會跟過來**，Next 本身漏掉不會報錯。要逐一接上的：
`metadata`、`generateMetadata`、`viewport`、`generateViewport`、`generateStaticParams`、`dynamic`、
`dynamicParams`、`revalidate`、`fetchCache`、`runtime`、`preferredRegion`、`maxDuration`、
`experimental_ppr`。
`tests/app/route-adapters.test.ts` 會比對兩邊；就地宣告頁面的例外列在 `IN_PLACE_PAGES`（只有首頁）。

前端有**兩個組裝點**：`config/routes.ts` 的 `ENABLED_MODULES`（路由、導覽、proxy 保護都從它推導）
與 `config/shell/nav-icons.ts` 的 `NAV_ICONS`（漏了會編譯失敗）。

### shared/ui

- 只從 `@/shared/ui` 匯出。需要 kit 的某個樣式時，在 kit 裡多包一個元件，不要讓 class 外流。
- **不要放帶 `server-only` 的東西**：client component 也會引用這個入口。
- **`"use client"` 只加在用到 state、effect、context 的檔案**；加互動就另開檔案，不在版面檔補指示詞（會把同檔元件全拖進 client bundle）。
- 間距用 `spacing()` 換成 `var(--space-n)`，不在元件裡算 px；`Flex` 沒帶的 prop 不輸出預設值，否則會蓋掉呼叫端的 class
  （`tests/shared/ui/ui.test.tsx` 守）。

## Backend module 介面

```text
modules/products/
├── manifest.py          # 必備。routers、tables、permissions
├── public.py            # 其他 module 唯一可引用的介面：函式與回傳型別，不放資料表
├── router.py
├── schema.py
├── service.py
├── model.py
└── permissions.py       # 有引入權限時才有 (users、roles 沒有: 後台只開放給超級管理者)
```

- **service 長大就依授權模型拆檔**，不開 `services/`。例：`modules/users/` 的 `service.py`（管理者對任意使用者）、
  `account.py`（使用者對自己）、`superuser.py`（建超管，只給 CLI），共用錯誤在 `errors.py`。
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
- **docstring 會外流到 API 文件**：route function、端點用的 pydantic model、進 schema 的 enum 的 docstring 會進 OpenAPI
  與前端型別檔，只寫給呼叫端看的；內部說明寫在模組層 docstring 或註解（`modules/users/schema.py` 開頭）。

### 兩份刻意中央化的清單

`app/permissions.py` 的 `Permission` 與 `shared/http/errors.py` 的 `Language` 是**僅有的兩處**
「新增功能要改共用檔案」的地方。它們要進 OpenAPI 成為字串聯集，前端才拿得到編譯期保護
（權限打錯字是 `tsc` 失敗，而不是執行期靜默失效），所以不要改成由模組動態貢獻
（[ADR 0003](decisions/0003-centralized-permission-and-language.md)）。

## 模組之間的資料關聯

跨模組的設計取捨（為什麼保留外鍵、允許共用交易）見 [ADR 0013](decisions/0013-cross-module-references-by-id.md)。

### 先決定怎麼切模組

**依關係緊密程度切，不是看有沒有外鍵**：幾乎所有業務資料都參照 users，有外鍵就合併的話最後只剩一個模組。

| 這樣的關係 → 放同一個模組 | 這樣的關係 → 分開，以 ID 參照 |
|---|---|
| 經常 JOIN、要用對方的欄位排序或篩選 | 只需要顯示對方的名稱 |
| 通常一起改 | 各自演進 |
| 有共同的規則要同時成立（訂單與明細的金額） | 只要求「指到的東西存在」 |
| 一方單獨存在沒有意義 | 各自都有獨立的意義 |

分開之後如果對方的 public 多到像是把內部原封不動轉出去，就是邊界畫錯了，應該合併。模組內部可以自由使用
ORM relationship、JOIN 與 `detail_loaders()`。

### 資料表與外鍵

| 關係 | 做法 | 放在哪個模組 |
|---|---|---|
| 多對一（訂單屬於使用者） | 外鍵欄位 `user_id` | 參照的一方 |
| 多對多（使用者的角色） | 關聯表 | 這個關係有業務意義的一方（`user_roles` 在 users） |
| 一對一擴充（替使用者加帳務資料） | 自己的表，`user_id` 加唯一約束 | 擴充的一方，**不在對方的表加欄位** |
| 歷史、稽核紀錄 | 只存 ID 與當時的快照，**不加外鍵** | 紀錄的一方，原始資料刪掉後紀錄仍要留著 |

- 外鍵用字串宣告（`ForeignKey("roles.id")`），不 import 對方的資料表。依賴方向跟外鍵方向一致，被參照的模組不知道誰在參照它。
- `ondelete` 由持有外鍵的一方決定：關聯表與擴充表 `CASCADE`；業務資料預設 `RESTRICT`；選填的關聯 `SET NULL`。
  `RESTRICT` 擋下的刪除，使用者會看到 409「仍有其他資料使用中」，不是 500。

### 讀對方的資料

- 只呼叫對方 `public.py` 的函式，拿到的是 `RoleDetail` 這類回傳型別，不是資料表。
- 一定要有**批次**版本（`find_role_details(ids)`），列表才不會每列查一次。補一整批資料時覆寫
  `BaseTable.to_details()`，`find_detail_*`、`get_all`、`get_page` 都經過它（例：`UserTable` 補角色）。
- 跨模組的函式不收 `session`，用目前的 session（`transaction()` 也會設定它），所以自然與呼叫端在同一個交易裡。
- 屬於對方的規則放在對方的 public，不在呼叫端各寫一份（例：停用的角色不給權限是 roles 的 `expand_permissions`）。

代價是比 JOIN 多一次查詢：身分來源每個請求固定三次（使用者、`user_roles`、roles），但不隨筆數增加
（`tests/modules/users/test_model.py` 鎖住）。

### 反方向的需求

被參照的一方需要知道誰在參照自己時（刪角色前檢查還有沒有人用、停用使用者時連動取消訂單），不可反過來 import：

1. 先交給資料庫：`RESTRICT` 讓刪除失敗。平台會把外鍵違反統一轉成 409：刪除時是「仍有其他資料使用中」，
   新增或更新時是「參照的資料不存在」（`shared/platform.py`），模組不必自己攔 `IntegrityError`。
   兩種情況 PostgreSQL 只有會隨語系變的 detail 文字不同，所以依觸發錯誤的 SQL 種類區分（`foreign_key_error()`）。
2. 需要明確的訊息或業務上的連動時，由持有外鍵的模組透過 manifest 提供，組裝層接上（同 `current_user_resolver`）。
   通用的 hook／事件機制**還沒有實作**，第一個真正需要的功能出現時再設計。

### 報表與跨模組的排序

| 需求 | 做法 |
|---|---|
| 資料量小、只是拼起來 | 報表模組呼叫各模組的 public，在 Python 裡組 |
| 加總、分組，只牽涉一個模組 | 由擁有資料的模組在 public 提供統計函式，計算在資料庫裡做 |
| 一定要跨模組 JOIN（用對方欄位排序後分頁、大量報表） | 在自己的表存去正規化的副本；或報表模組擁有**唯讀的資料庫 view**，在它的 public 與 ADR 寫明是例外 |

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

兩份產出都進版控，對外介面的變更在 review 的 diff 裡看得到。只有 `make gen-types` 寫進 repo；`make check contract` 與
`make release` 重產到暫存目錄再比對，不一致就擋，不改工作目錄（`scripts/lib/contract.sh`）。
什麼時候要跑 `make gen-types` 見 [`development.md`](development.md#指令)。
兩個檔案的路徑只定義在 `scripts/lib/common.sh` 的 `CONTRACT`、`WEB_SCHEMA`。

OpenAPI 的 `info.version` 固定是 `"1"`：規格要求必填，但前後端在同一個 repo、一起部署，
沒有人讀它；契約變了什麼看 `contracts/openapi.json` 的 diff。

## 新增與移除 module

新增的步驟見 [`extending/new-module.md`](extending/new-module.md)。原則：前後端同名；public entry
從**最小**開始設計；業務 entity 型別一律在用到它的模組的 `types.ts` 以 `Schema<"…">` 命名，
不搬進 shared，刪掉模組時型別才會跟著消失。

**一個模組要能整包刪掉，而且不必改 `shared/`**：

| 位置 | 動作 |
|---|---|
| `apps/api/modules/<name>/`、`apps/api/tests/modules/<name>/` | 整包刪除 |
| `apps/api/app/registry.py`、`app/permissions.py` | 移除 manifest 與 enum 成員 |
| `apps/web/modules/<name>/`、`apps/web/tests/modules/<name>/`、`apps/web/app/(protected)/(<區>)/<path>/` | 整包刪除 |
| `apps/web/config/routes.ts`、`config/shell/nav-icons.ts` | 移除 manifest 與圖示 |

權限的標籤與分類跟著模組的 `permissions.py` 一起消失，角色畫面不必改。收尾**先 `make gen-types`
再 `make check types`**，前端還在用的已刪除端點或權限才會變成編譯錯誤。另外清掉 `apps/web/.next`
（否則 `tsc` 會找已刪除路由的型別），帶環境變數的模組要把
[同步點](development.md#環境變數的同步點)一起縮小。

`users` 依賴 `roles` 的公開面（顯示角色名稱），這兩個是核心模組，實務上不會刪。

## 前後端 shared 的約定

前後端的 shared 是**一對**：前端假設後端的錯誤格式、`Accept-Language`、`X-Request-ID` 與 token
cookie 的協定，也假設 OpenAPI 裡一定有 `Permission` 與 `Language` 兩個 schema
（`shared/api/entities.ts` 從它們衍生型別，少了就是 `tsc` 錯誤）。
前端 shared 另外要求專案在 `LOGIN_PATH` 提供登入頁並認得 `?reason=`，約定寫在
`apps/web/shared/session/login-contract.ts`（這個模板由 `modules/auth` 提供）。

shared 的設計變數在 `shared/ui/styles/tokens.css` 給預設值，專案只在 `app/theme.css` 覆寫
（`tests/shared/ui/tokens.test.ts` 擋只定義在專案裡的變數）。

