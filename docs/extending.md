# 擴充指南

「要做 X 該怎麼做」的步驟。依賴邊界與模組介面的**規則**在 [`architecture.md`](architecture.md)。

範例一律照抄現成模組，兩邊都從 **roles** 開始（標準的 CRUD：列表、建立、修改、停用）：
後端 `apps/api/modules/roles/`、前端 `apps/web/modules/roles/`。需要更進一步的寫法時再參考
users：關聯表與篩選（`model.py`）、依授權模型拆檔（`service.py`／`account.py`／`bootstrap.py`）。

## 新增一個功能模組

以 `products` 為例，照順序做。**前後端模組同名。**

### 1. 後端模組

1. 複製 `apps/api/modules/roles/` 為 `modules/products/`，改成自己的 router、schema、service、
   `ProductTable` 與 `permissions.py`。
2. 在 `manifest.py` 宣告 routers、tables 與 permissions，再加進 `app/registry.py` 的
   `ENABLED_MODULES`。
3. 照 `modules/roles/` 的慣例寫：

   ```python
   # router.py —— route function 一律 *_route 結尾，只做權限守衛的參數也要標型別
   @router.patch("/{id}")
   async def update_product_route(
       id: str,
       form_data: ProductUpdate,
       _: CurrentUser = Depends(check_user_permission(Permission.PRODUCT_UPDATE)),
   ) -> ProductOperate:
       return await service.update_product(id, form_data)

   # service.py —— 模組層級的函式；收 pydantic model 而不是 dict，回傳建構好的 model
   async def update_product(id: str, form_data: ProductUpdate) -> ProductOperate:
       ensure_found(await ProductTable.find_detail_by_id(id), ProductError.NOT_FOUND)
       await ProductTable.update_by_id(id=id, data={"name": form_data.name})
       return ProductOperate(id=id)
   ```

   - 寫入時**逐欄列出**要寫的資料，不要 `**form_data.model_dump()`：日後新增的欄位會自動落地，
     包含不該落地的（見 `modules/roles/service.py` 的 `create_role`）。
   - 回應裡的時間欄位用 `shared.http.schema` 的 `UtcDateTime`。裸的 `datetime` 序列化出去沒有
     時區，瀏覽器會當成本地時間。
   - 取單筆用 `BaseTable.find_detail_by_id(id)`。**不要**自己呼叫 `find_detail_one()`：它不會
     自己加條件，忘了補會回傳資料表裡的第一筆。
4. 測試放 `apps/api/tests/modules/products/`，照抄 `tests/modules/roles/`：`test_routes.py`
   （權限依賴、狀態碼、回應形狀）與 `test_service.py`（業務規則、寫入的欄位）。

### 2. 權限

1. 在 `apps/api/app/permissions.py` 的 `Permission` enum 加成員（`PRODUCT_READ = "products:read"`）。
   這是刻意中央化的清單，理由見 [`architecture.md`](architecture.md#兩份刻意中央化的清單)。
2. label（動作，例「查看」）、category（分類，例「商品」）、dependencies、assignable 寫在
   `modules/products/permissions.py`，由 manifest 註冊；宣告順序就是角色畫面上的順序。
   enum 與 metadata 對不上時，api 會在啟動時直接失敗。
   角色編輯畫面直接用後端給的標籤與分類（`GET /roles/permission-options`），**前端不必改**。

### 3. Migration

```bash
make db migration "add products"
```

**產生之後自己讀一遍**，注意事項見〈[Migration 注意事項](#migration-注意事項)〉。

### 4. 產生前端型別

```bash
make gen-types
```

`contracts/openapi.json` 與 `apps/web/shared/api/generated/schema.d.ts` 兩份都要 commit。
前端的 `Permission` 型別、端點與 entity 型別都會跟著更新。

### 5. 前端模組

1. 複製 `apps/web/modules/roles/` 為 `modules/products/`。資料、actions、能力判斷留在模組根，
   畫面放 `ui/`，模組內部一律相對路徑。
2. 在 `manifest.ts` 宣告路由（`as const` 與 `satisfies` 兩個都要，少了前者型別保護就沒了）。
   `group` 決定它在使用者區（`"user"`）還是管理區（`"admin"`）。管理區只開放給超級管理者，
   `"admin"` 的路由一律寫 `requires: ["*"]`（測試會擋）。`showInNav: false` 的頁面照樣受保護，
   只是不出現在導覽列（例如設定頁，入口在頭像選單）：

   ```ts
   export const PRODUCTS_ROUTE = {
     path: "/products", label: { zh: "商品", en: "Products" },
     group: "user", requires: ["products:read"], navIcon: "products", showInNav: true,
   } as const satisfies ProtectedRoute

   export const PRODUCTS_MODULE = {
     name: "products", protectedRoutes: [PRODUCTS_ROUTE],
   } as const satisfies ModuleManifest
   ```

3. **兩個組裝點都要加**：`config/routes.ts` 的 `ENABLED_MODULES`，以及
   `config/shell/nav-icons.ts` 的 `NAV_ICONS`。漏了圖示會編譯失敗；**漏了 `ENABLED_MODULES`
   不會** —— 頁面照樣渲染，只是沒有導覽也沒有 proxy 保護。
4. 在 `public.server.ts` 具名轉出頁面、`generateMetadata` 與 props 型別，再在**對應區**的
   目錄底下建薄 route adapter（`group: "user"` 放 `(user)/`；`"admin"` 放 `admin/`，`path` 也要以 `/admin/` 開頭）：

   ```tsx
   // app/(protected)/(user)/products/page.tsx
   import {
     ProductsPage, generateProductsMetadata, type ProductsPageProps,
   } from "@/modules/products/public.server"

   export const generateMetadata = generateProductsMetadata

   export default function Page(props: ProductsPageProps) {
     return <ProductsPage {...props} />
   }
   ```

   **Next 特有的 export 要逐一接上，漏掉沒有錯誤訊息**，清單見
   [`architecture.md`](architecture.md#frontend-module-介面)。
5. 模組的 server page 自己再用 `canAccessRoute(permissions, PRODUCTS_ROUTE)` 擋一次（引用自己
   manifest 的常數；模組不能引用 `config/`）。layout 只做粗篩，真正的授權在後端。
6. 列表頁直接複用：`shared/pagination` 的 `parsePagination()`、`fetchPaginatedList()`；
   `@/shared/ui` 的 `ListPageHeader`、`ListTableCard`、`TableRow`、`FilterDialog`、`FormDialog`、
   `useListFeedback`、`useActionSubmit`。create／edit 對話框各自一個元件檔。
7. 畫面裡有分支邏輯時抽進 `capabilities.ts`，測試放 `apps/web/tests/modules/products/`。

### 6. 檢查

```bash
make check               # lint + types + test + build + portable
make check integration   # 需要資料庫的測試 + model 與 migration 一致
```

## 把 shared 帶到另一個專案

兩邊的 `shared/` 可以整包複製到另一個專案直接使用（承諾與限制見
[`architecture.md`](architecture.md#shared-的可移植性)）。前提是新專案沿用同一條技術線：
後端 FastAPI + SQLAlchemy 2.0 async（PostgreSQL），前端 Next.js App Router + React。
shared 綁著這裡的版本，升級時一起升。

### 後端

1. 複製 `apps/api/shared/` 與 `apps/api/tests/shared/`，連同 `tests/` 根目錄的 `__init__.py`、
   `conftest.py`、`integration.py`。第三方相依：`fastapi`、`sqlalchemy[asyncio]`、`asyncpg`、
   `pydantic`、`PyJWT`、`bcrypt`（版本見 `apps/api/pyproject.toml`）。
2. 組裝層提供三樣東西，再呼叫 `shared/platform.py` 的 `create_platform_app()`（範例：`app/server.py`）：
   - 滿足 `PlatformEnv` 的設定物件：`project_name`、`postgres_url`、`jwt_secret_key`、
     `jwt_algorithm`、`expire_hours`、`token_version`（範例：`app/config.py`）。
   - 繼承 `BasePermission`、含一個 `ALL = WILDCARD` 成員的權限 enum（範例：`app/permissions.py`）。
   - 啟用的 module manifest 清單（範例：`app/registry.py`）。
3. 要用 `check_user_permission()` 的話，某一個 module 的 manifest 要提供 `current_user_resolver`
   （回傳 `shared/auth/contracts.py` 的 `CurrentUser`，範例：`modules/users/manifest.py`），
   token 用 `shared/auth/tokens.py` 的 `create_token()` 簽發。
4. OpenAPI 裡要有 `Permission` 與 `Language` 兩個 schema，前端 shared 靠它們產型別：
   `Permission` 只要有任何 schema 欄位標成它就會進去；`Language` 沿用 `modules/languages/`
   （或照 `tests/shared/minimal_app.py` 的寫法自己帶進去）。

### 前端

1. 複製 `apps/web/shared/` 與 `apps/web/tests/shared/`，連同 `tests/setup.ts`、`tests/stubs/`，
   以及 `vitest.config.ts` 裡把 `server-only` 換成 stub 的 alias。第三方相依：`next`、`react`、
   `lucide-react`。`tsconfig.json` 的 `@/*` 要指到專案根。
2. 從後端產生 `shared/api/generated/schema.d.ts`（`make gen-types` 的做法見 `scripts/gen-types.sh`）。
3. 文件根依序載入 `shared/ui/styles/` 的 `tokens.css` → 專案的 `theme.css` → `base.css` →
   `message-page.css`，並包上 `LocaleProvider`、`PublicConfigProvider` 與 `NotifyViewport`
   （範例：`app/layout.tsx`）。`global-error.tsx` 在 root layout 之外，要自己再載一次 `tokens.css`。
4. 在 `shared/session/login-contract.ts` 的 `LOGIN_PATH` 提供登入頁並認得 `?reason=`，
   路由保護以 `ACCESS_TOKEN_COOKIE` 判斷有沒有登入（範例：`modules/auth/`、`proxy.ts`）。
5. 執行期環境變數：`API_URL`（後端位址）、`EXPIRE_HOURS`（cookie 壽命，與後端同一個值）、
   `SYSTEM_NAME`（顯示名稱）。

### 確認

`make check portable` 做的就是上面這件事的自動版：把兩邊的 shared 複製到空目錄，後端跑 mypy 與
pytest，前端用只有平台 schema 的契約跑 `tsc` 與 vitest。新專案可以把 `scripts/check.sh` 的
`run_portable` 連同 `apps/api/tests/shared/minimal_app.py` 一起帶走。

**在新專案修了 shared 的錯，記得回到模板也修一次**，否則兩份會各自漂移，下次移植又要重踩一遍。

## 分頁、篩選與交易

`BaseTable`（`apps/api/shared/db/table.py`）的列表方法**依「要不要分頁」二選一**：

| 方法 | 回應型別 | 用在 |
|---|---|---|
| `get_page(limit=…, cursor=…, where=[…])` | `PaginatedResponse[T]` | 資料量會成長的列表（游標分頁） |
| `get_all()` | `SimpleListResponse[T]` | 天然有限的清單，例如下拉選單（範例：`GET /roles/options`） |

- 篩選條件放 `where`，它會同時套用在資料與 `total_count` 上。
- 補關聯資料覆寫 model 的 `detail_loaders()`（回傳 `selectinload(...)`）與 `to_detail()`，
  範例見 `modules/users/model.py` 的 `find_list()`。
- 多個寫入要一起成功或失敗時，用 `shared/db/transaction.py` 的 `transaction()` 包住，並把
  `session` 傳給各 model 方法。交易**防不了**兩個請求各自新增重複資料，那要靠唯一約束。
  在請求裡它是一個 SAVEPOINT：區塊失敗只撤銷區塊內的寫入，成功也**不會提前 commit**，
  整個請求最後回錯誤時一樣全部回滾。

## 呼叫 API

前端的回應型別**由 `url` 推導**，不要自己指定：

```ts
const res = await apiGet({ url: "/roles/{id}", params: { id } })
if (res.status === "success") res.data.name   // 已窄化成 RoleInfo
else res.data.detail                          // 已窄化成錯誤形狀

// Server Action 的 payload 型別同樣從後端 schema 衍生
export async function updateRole(id: string, data: ApiRequestBody<"/roles/{id}", "patch">) {
  return apiPatch({ url: "/roles/{id}", params: { id }, data, refresh: refreshRoles })
}
```

- 路徑寫成**模板**（`/roles/{id}` + `params`），不是樣板字串 —— url 是字面值型別才推得出來。
  端點、方法、參數或 body 寫錯都會在 `tsc` 階段失敗。
- **收密碼或金鑰的 action 改收 `FormData`**（`shared/api/action-form-data.ts`）：Next 的開發
  log 會展開一般參數。
- **會寫 session cookie 的 action 回傳前要經過 `withoutAccessToken`**：Server Action 的回傳值會
  送進瀏覽器（`tests/token-cookie-writers.test.ts` 會擋）。
- 業務 entity 在模組的 `types.ts` 以 `Schema<"RoleInfo">`（`@/shared/api/contract`）命名，不手寫
  形狀，也不放進 shared；`@/shared/api/entities` 只有平台型別（`Permission`、`Language`、分頁形狀）。
- 需要目前登入者時用 `@/modules/auth/public.server` 的 `getCurrentUser()`；密碼規則在
  `@/modules/auth/public.client`。

## Migration 注意事項

資料表**只由 migration 建立**（Alembic，revision 在 `apps/api/migrations/versions/`）。
漏寫 migration 時所有單元測試都是綠的，只有 `make check integration` 與 CI 會擋。

autogenerate 固定會漏三件事，產出一定要讀：

| 它漏掉的 | 你要補的 |
|---|---|
| 往有資料的表加 NOT NULL 欄位，它只寫 `ADD COLUMN` | 給 `server_default`，或補一段回填 |
| 改名會被看成「drop 一個、add 一個」 | 改寫成 `op.alter_column(..., new_column_name=...)` |
| 不能在交易裡跑的 DDL（`CREATE INDEX CONCURRENTLY`） | 當成獨立的維運操作 |

- **migration 不會隨程式碼回退**。改名與刪除要拆成兩次發版：先加新的、兩邊並存，下一版才刪舊的。
- 保持**一個 head**（`tests/test_migrations.py` 守），分岔了用 `alembic merge`。
- migration 裡**不要 import model**，用 `sa` 與 `op`；不要自己開交易或 `COMMIT`。
- 資料回填寫在 migration，不要寫進 `shared/platform.py` 的 lifespan。

## 初始資料（Seed）

定義在 model class 上，服務啟動時由 `BaseTable.ensure_seed()` 寫入：

| class variable | 說明 |
|---|---|
| `seed_data` | 初始資料的 `list[dict]` |
| `seed_match_key` | **有設**：每次啟動依此欄位 upsert（欄位必須有唯一約束）；**沒設**：只在表為空時寫入 |
| `prepare_seed_item()` | 選用，寫入前轉換資料（例如雜湊密碼） |

`RoleTable` 設了 `seed_match_key = "code"`，所以新增的權限會自動補進已在跑的環境裡的超管角色。

## 語系（i18n）

前後端同一個語系：語系存在 `locale` cookie，每個 API 請求都帶 `Accept-Language`，
後端的錯誤訊息跟著 UI 走。

**字串放在擁有它的那一層的 `i18n.ts`**，沒有全站字典：

| 字串屬於 | 放哪裡 |
|---|---|
| 某個模組 | `modules/<name>/i18n.ts` |
| UI kit | `shared/ui/i18n.ts` |
| 外殼、首頁、錯誤頁 | `config/i18n.ts` |

```typescript
// modules/foo/i18n.ts —— 漏翻譯或多一個 key 都會編譯失敗
export const fooMessages = defineMessages({
  zh: { title: "標題", greet: "你好，{name}" },
  en: { title: "Title", greet: "Hello, {name}" },
})

const t = await getT(fooMessages)            // Server Component
const t = useT(fooMessages)                  // client component
const t = translate(fooMessages, locale)     // 純函式：收 locale 當參數
t("greet", { name })
```

- **manifest 的 `label` 直接寫 `{ zh, en }`**，不走字典
  （manifest 要 edge-safe，沒有 React context）。頁面標題用 `generateMetadata()`。
- **後端**的訊息用 `shared/http/errors.py` 的 `LangText(zh=…, en=…)`；`LangException` 會依請求
  語系自動取字，不能丟例外的地方（pydantic validator）用 `resolve_text()`。
- 後端直接送到畫面的其他文字（推播、事件訊息）也要走 `LangText` + `resolve_text()`，而且
  **只在收件人就是發起請求的人時才成立** —— 送給多人時改成只帶 type + id，讓前端自己組文案。
- **加第三種語言**：從後端 `Language` enum 開始，`make gen-types` 之後 `tsc` 會列出前端所有
  要跟上的地方。

## 更換視覺／導入 Design System

設計變數的**名字與預設值**在 `apps/web/shared/ui/styles/tokens.css`，那是 UI kit 與各模組 CSS
module 共用的契約，跟著 shared 走。**這個專案的外觀在 `apps/web/app/theme.css` 覆寫**：只寫要改的
那幾個變數，名字不要自創。導入 Design System 時把 theme.css 的右手邊改成 DS 的值或變數即可。
需要新的變數時先加進 tokens.css（給預設值），再在 theme.css 覆寫。底色改了要同步
`apps/web/app/manifest.ts` 的 `theme_color`。
