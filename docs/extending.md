# 擴充指南

用這個模板開新案時，可以加上的擴充項目與做法。內建功能怎麼運作見 [`features/`](features/README.md)，
依賴邊界與模組介面的**規則**在 [`architecture.md`](architecture.md)。

範例一律照抄現成模組，兩邊都從 **roles** 開始（標準的 CRUD：列表、建立、修改、停用）：
後端 `apps/api/modules/roles/`、前端 `apps/web/modules/roles/`。需要更進一步的寫法時再參考
users：關聯表與篩選（`model.py`）、依授權模型拆檔（`service.py`／`account.py`／`superuser.py`）。

## 新增一個功能模組

以 `products` 為例，照順序做。**前後端模組同名。**

### 1. 後端模組

1. 複製 `apps/api/modules/roles/` 為 `modules/products/`，改成自己的 router、schema、service 與
   `ProductTable`。roles 沒有 `permissions.py`（後台只開放給超級管理者），照〈[2. 權限](#2-權限)〉新增。
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
   欄位的意思見 `shared/module.py` 的 `PermissionSpec`：

   ```python
   # modules/products/permissions.py
   from app.permissions import Permission
   from shared.http.errors import LangText
   from shared.module import PermissionSpec

   CATEGORY = LangText(zh="商品", en="Products")

   PERMISSIONS = (
       PermissionSpec(Permission.PRODUCT_READ, LangText(zh="查看", en="View"), CATEGORY),
       PermissionSpec(
           Permission.PRODUCT_UPDATE,
           LangText(zh="修改", en="Edit"),
           CATEGORY,
           dependencies=frozenset({Permission.PRODUCT_READ}),  # 能改就要能看
       ),
   )

   # modules/products/manifest.py
   MODULE = ModuleManifest(
       name="products", routers=(router,), tables=(ProductTable,), permissions=PERMISSIONS,
   )
   ```

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
   `config/shell/nav-icons.ts` 的 `NAV_ICONS`。漏了圖示會編譯失敗；漏了 `ENABLED_MODULES`
   由 `tests/config/routes.test.ts` 擋（頁面在 `app/` 裡卻不在路由清單上）。
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

   **Next 特有的 export 要逐一接上**：Next 本身漏掉不會報錯，由 `tests/app/route-adapters.test.ts` 擋，
   清單見 [`architecture.md`](architecture.md#frontend-module-介面)。
5. 模組的 server page 自己再用 `canAccessRoute(permissions, PRODUCTS_ROUTE)` 擋一次（引用自己
   manifest 的常數；模組不能引用 `config/`）。layout 只做粗篩，真正的授權在後端。
6. 列表頁直接複用：`shared/pagination` 的 `parsePagination()`、`fetchPaginatedList()`；
   `@/shared/ui` 的 `ListPageHeader`、`ListTableCard`、`TableRow`、`FilterDialog`、`FormDialog`、
   `useListFeedback`、`useActionSubmit`。create／edit 對話框各自一個元件檔。
7. 畫面裡有分支邏輯時抽進 `capabilities.ts`，測試放 `apps/web/tests/modules/products/`。

### 6. 檢查

```bash
make check               # lint + contract + migrate + types + test + build
make check integration   # 需要資料庫的測試 + model 與 migration 一致
make check e2e           # 畫面流程有改時：拋棄式正式環境 + Playwright
```

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

## 上傳檔案

上傳的檔案（圖片、影片、文件）一律存在 api 的 **`/app/uploads/<模組>/`** 底下，例如
`/app/uploads/products/`。那裡掛的是 uploads volume，`make backup` 備份的就是它
（見 [`operations.md`](operations.md#備份與還原)）。

- **存到別的路徑不會有任何錯誤**：上傳、讀取都正常，但容器一重建檔案就消失，備份裡也不會有。
- 一個模組一個子目錄，不要每個模組開自己的 volume：多一個 volume 就要多改一次 compose 與備份腳本。
- 資料庫裡存**相對於 `/app/uploads` 的路徑**（`products/<id>.jpg`），不存絕對路徑：之後換掛載點或改用
  物件儲存時，資料不用跟著改。
- 檔名由後端產生（例如 id），不要直接用使用者給的檔名：可能撞名，也可能帶 `../`。

### 大小上限

整個請求（檔案加上其他欄位）**固定上限 16MB**，不開放設定：nginx 的 `client_max_body_size` 與 Next 的
`serverActions.bodySizeLimit` 都是這個值（`apps/web/tests/next.config.test.ts` 確保兩邊一致）。
它只是防護用的天花板，超過時使用者只會看到一般錯誤，**看不到說明**。所以每個上傳功能都要自己決定上限：

- **上限寫成功能裡的常數**（例如大頭貼 2MB），不要做成環境變數。
- **以後端的檢查為準**：超過時回傳 `LangText` 錯誤訊息（見〈[語系](#語系i18n)〉）。
- **前端送出前也檢查一次**：選了檔案就比對大小，不必等整個檔案傳完才被拒絕。
- 功能的上限要**小於 16MB**，並預留其他欄位與 multipart 編碼的空間。

**需要超過 16MB 的檔案（影片、大型壓縮檔）時，不要把天花板調高**：Server Action 會把整個 body 讀進
web 容器的記憶體，轉送到後端時又多一份，而正式環境的 web 只有 512MB。這時改用串流上傳（在 nginx
為該端點開一條專屬 location 直接轉到 api），或用物件儲存的 presigned URL 讓瀏覽器直傳。

前面有主機的 reverse proxy 時，它的 `client_max_body_size` 不能小於 16MB（nginx 預設只有 1MB），
否則超過的請求在主機那層就被擋下。

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

- **兩版之間多了 migration 就不能回滾**，部署前的檢查會拒絕（見
  [`operations.md`](operations.md#回滾與-migration)）。
- 改名與刪除仍建議拆成兩次發版（先加新的、兩邊並存，下一版才刪舊的）：部署時 migrate 先跑、
  程式後換，中間幾秒舊程式會跑在新結構上。
- 保持**一個 head**（`tests/test_migrations.py` 守），分岔了用 `alembic merge`。
- migration 裡**不要 import model**，用 `sa` 與 `op`；不要自己開交易或 `COMMIT`。
- 資料回填寫在 migration，不要寫進 `shared/platform.py` 的 lifespan。

### 發版之前可以整理

部署只認 release（[`operations.md`](operations.md#自動部署)），所以還沒發布的 migration 不在任何主機上。
`make check migrate` 以**最近的 `v*` tag** 為界（prerelease 的 `v0.2.0-rc.1` 也算）：

| migration | 可以怎麼改 |
|---|---|
| 還沒有任何 tag（發 0.0.1 之前） | 全部都能改，結構變更直接併回初始 migration |
| 最近的 tag 之後才新增 | 合併、改寫、刪除都可以：同一個功能開發中途改了幾次結構，發版前併成一支 |
| 最近的 tag 之前就有 | **只往前**，不可修改或刪除，要改結構就新增一支 |

整理的步驟：把要合併的幾支改寫成一支（`down_revision` 接回 tag 時的 head），刪掉其餘的，
再 `make db reset` 重建本機資料庫，最後 `make check integration`（`alembic check` 確認與 model 一致）。

- **一起開發的人也要 `make db reset`**：他們的資料庫可能停在被刪掉的 revision，`migrate` 會找不到它而失敗。
- **prerelease 發出去之後就不能再整理**：它會部署到 staging，那裡的資料庫已經跑過這些 migration。

## 初始資料（Seed）

定義在 model class 上，由 **migrate 服務**在 `alembic upgrade head` 之後以 `BaseTable.ensure_seed()`
寫入（`scripts/db.py migrate`）。`make start`、`make db migrate`、`make db reset` 都會經過它；
api 開機時**不寫任何資料**（[ADR 0007](decisions/0007-seed-in-migrate-service.md)）。所以 seed 失敗跟 migration 失敗一樣，會被 `make start`「migrate 失敗就不切換服務」
擋下（見 [`operations.md`](operations.md#生產部署)）：


| class variable | 說明 |
|---|---|
| `seed_data` | 初始資料的 `list[dict]` |
| `seed_match_key` | **有設**：每次 migrate 都依此欄位 upsert（欄位必須有唯一約束，多個行程同時跑也安全）；**沒設**：只在表為空時寫入（同時跑會重複寫入，只能在一個行程裡跑） |
| `prepare_seed_item()` | 選用，寫入前轉換資料（例如雜湊密碼） |

`RoleTable` 設了 `seed_match_key = "code"`，所以系統角色的權限與名稱在每次部署時都會同步回模板的定義。
改了 `seed_data` 之後，開發機跑 `make db migrate` 就會套用。

## 背景工作（尚未內建）

寄信、匯出報表、排程這類不該卡住請求的工作，模板還沒有提供，但方向已經定了
（[ADR 0006](decisions/0006-postgres-job-queue.md)），加的時候照這個做：

- **另開一個 worker 容器**，跟 `migrate` 一樣用 api 的 image、換一個 command，程式與 model 共用。
- **佇列放 PostgreSQL**（`SELECT … FOR UPDATE SKIP LOCKED`），**不導入 Redis**：少一個要維運與備份的
  服務，而且任務能跟業務資料寫在**同一個交易**裡，不會出現「資料沒寫進去、信卻寄出去了」。
  排程（每天固定時間跑）也放在同一個 worker，不另開容器。
- **每個任務要自己開 session**：HTTP 請求的 session 由 middleware 開，worker 沒有這一層，
  由 worker 的框架統一包 `session_scope()`，不要讓每個任務自己記（見 `shared/db/session.py`）。
- **worker 不跑 seed**：seed 屬於 migrate 服務，只在部署時跑一次（見〈[初始資料](#初始資料seed)〉）。
- **任務要能重跑**：worker 可能在做到一半時被重啟（部署、OOM），重跑一次不能出錯或重複寄信。
- **任務由模組在 `manifest.py` 宣告**，worker 從 `ENABLED_MODULES` 收集（比照 router），
  模組整包刪掉時任務才會跟著消失。

## 語系（i18n）

語系怎麼在前後端之間傳遞見 [語系](features/i18n.md)。

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
