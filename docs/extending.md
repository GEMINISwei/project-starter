# 擴充指南

「要做 X 該怎麼做」的操作手冊。**依賴邊界與模組介面的規則**在
[`architecture.md`](architecture.md)，這裡只講步驟。

> **先看範例模組。** 前後端的 `modules/items/` 是刻意保持最小的完整範例，
> 涵蓋資料表 model、游標分頁、關聯載入、篩選、權限、WebSocket 通知、列表頁與對話框。
> 底下每一節說「複製 items」時，指的都是它。
>
> **`items` 是刻意可刪的**（見 `TEMPLATE.md` 第 2 步）。已經刪掉的話，這份文件裡
> 每一處 `modules/items/` 都可以改看 `modules/users/`（後端）或 `modules/roles/`（前端）——
> 除了「新增 WebSocket 事件」那一節，那裡 `items` 是 repo 內唯一的事件發送端，
> 只能照著描述寫。`make check-docs` 會把懸空的指路逐行列出來。

## 新增前端頁面

1. 複製 `apps/web/modules/items/` 為新模組目錄。資料載入、actions、能力判斷、型別與
   該功能的 WS handler 留在模組根，畫面放 `ui/`；模組內部一律相對路徑。

2. 在模組的 edge-safe `manifest.ts` 宣告路由：

   ```ts
   export const PRODUCTS_ROUTE = {
     path: "/products", label: { zh: "商品", en: "Products" },
     group: "general", requires: ["products:read"], navIcon: "products",
   } as const satisfies ProtectedRoute

   export const PRODUCTS_MODULE = {
     name: "products",
     protectedRoutes: [PRODUCTS_ROUTE],
   } as const satisfies ModuleManifest
   ```

   `as const` 與 `satisfies` 兩個都要：少了 `satisfies` 型別不會被檢查，
   少了 `as const` 欄位會被放寬成 `string`，`getRoute()` 與 `NAV_ICONS` 的編譯期保護就沒了。
   `label` 是 `LocaleText`（`{ zh, en }`）而不是字串 —— manifest 要保持 edge-safe，
   那一層沒有字典可查，理由見下面的〈[語系（i18n）](#語系i18n)〉。

3. 把 manifest 加進 `config/routes.ts` 的 `ENABLED_MODULES`，並在
   `config/shell/nav-icons.ts` 的 `NAV_ICONS` 登錄圖示 —— **有導覽的模組這兩處都要加**。
   route 與 icon 的 literal union 由啟用的 manifest 推導，漏了圖示會直接編譯失敗。

4. 在 `public.server.ts` 具名轉出頁面、`generateMetadata` 與 props 型別，再於 `app/(protected)`
   建立薄 route adapter：

   ```tsx
   // app/(protected)/products/page.tsx
   import {
     ProductsPage, generateProductsMetadata, type ProductsPageProps,
   } from "@/modules/products/public.server"

   export const generateMetadata = generateProductsMetadata

   export default function Page(props: ProductsPageProps) {
     return <ProductsPage {...props} />
   }
   ```

   頁面標題用 `generateMetadata` 而不是靜態的 `metadata`，因為標題要跟著當下語系走 ——
   靜態 `metadata` 在請求進來前就算好了，讀不到 cookie 裡的語系。

   **Next 只讀 route 檔的 export，模組裡的不會自己跟過來，而且漏掉沒有錯誤訊息。**
   用到 `generateMetadata`、`revalidate`、`dynamic` 之類的 route segment config 時要逐一接上；
   完整清單與 `route-adapters.test.ts` 的檢查方式見
   [`architecture.md`](architecture.md#frontend-module-介面)。

5. 模組的 server page 自己再用 `canAccessRoute(permissions, getRoute("/products"))` 擋一次。
   layout 只做粗篩，使用者仍可能手動輸入網址；真正的授權一律在後端。

6. 列表頁不要從頭寫，直接複用：

   - `shared/pagination`：`parsePagination()`、`parseBooleanFilter()`、`fetchPaginatedList()`
   - `@/shared/ui` 版面樣板：`ListPageHeader`、`ListTableCard`、`TableRow`、`FilterDialog`
   - `@/shared/ui` hooks：`useListFeedback`、`useActionSubmit`
   - `@/shared/ui` 元件：`FormDialog`、`useActiveStatusOptions`、`useStatusFilterOptions`
     與表單 primitives（狀態選項是 hook 而不是常數，因為選項文字要在地化）

   UI kit 一律 `import { X } from "@/shared/ui"`，不要指進 `shared/ui/` 的子路徑
   （`check:architecture` 會擋）。慣例：每個 create/edit 對話框各自獨立成一個元件檔
   （`CreateXxxDialog.tsx`／`EditXxxDialog.tsx`），不要內嵌在 View 裡。

## 新增 API 模組

1. 複製 `apps/api/modules/items/` 為 `modules/products/`，讓 router、schema、service、
   `ProductTable`、permission metadata 與 public entry 維持在同一個功能內。

2. 在 `manifest.py` 宣告 routers、tables 與 permission metadata，再把 manifest 加到
   `app/registry.py` 的 `ENABLED_MODULES`。這是明確清單，不使用檔案掃描。

   **新增一整張資料表不必寫 migration** —— `make migrate` 會依 model 定義補上還不存在的
   表與索引。但**改既有的表一定要寫**（見下面「資料庫 migration」）。

3. 列表端點複用 `shared.http.schema` 的分頁 schema，以及 `shared.db` 的
   `pagination_indexes()`、`ilike_contains()` 與交易能力：

   ```python
   # router.py
   @router.get("/")
   async def get_product_list_route(
       pagination: Annotated[PaginationParams, Depends()],
       _=Depends(check_user_permission(Permission.PRODUCT_READ)),
   ) -> ProductList:
       return await service.get_product_list(**pagination.model_dump())

   # schema.py
   class ProductList(PaginatedResponse["ProductInfo"]):
       pass
   ```

   schema 是**扁平的類別**、service 是**模組層級的函式**（`from . import service`），
   沒有命名空間類別也沒有 service 類別 —— 對照 `modules/items/schema.py` 與
   `modules/items/router.py`。HTTP route function 一律 `*_route` 結尾，
   與同名的 service 函式區分開（`modules/realtime/router.py` 的 `websocket_endpoint`
   走 `@router.websocket`，不是 HTTP 路由，不適用這條）。

4. **Service 的參數慣例**：id 直接當具名參數傳，表單資料傳 `schema.py` 的 pydantic model
   本身，不要在 router 呼叫 `.model_dump()` 之後丟一包 dict 進去：

   ```python
   # router.py
   return await service.update_product(id, form_data)

   # service.py
   async def update_product(id: str, form_data: ProductUpdate) -> ProductOperate:
       ensure_found(await ProductTable.find_detail_by_id(id), ProductError.NOT_FOUND)
       await ProductTable.update_by_id(id=id, data={"name": form_data.name})
       return ProductOperate(id=id)
   ```

   這樣欄位名打錯、schema 改欄位而 service 沒跟上，都會在 mypy 就被擋下來。

   要在寫入前轉換某些欄位（例如密碼必須先雜湊）時，請**逐欄列出**要寫入的資料，
   不要用 `**form_data.model_dump()` 再覆蓋幾個鍵：那種寫法會讓日後新增的欄位自動落地，
   包含不該落地的（實例見 `modules/users/service.py` 的 `create_user`）。

5. Service 回傳**建構好的 pydantic model**，不是 dict，而且**要寫回傳型別註記**。
   寫了註記，回傳 dict 會被 mypy 的 `return-value` 擋下；但 `modules.*` 沒有開
   `disallow_untyped_defs`（只有 `shared.*`／`app.*` 有，見 `pyproject.toml`），
   **漏寫註記不會有任何提示**，那個函式就完全不受檢查。這一條靠註記自覺，不是靠設定。

6. 要以 id 取單筆加工過的資料，用 `BaseTable.find_detail_by_id(id)`；需要補關聯資料時
   覆寫 `detail_loaders()`（回傳 `selectinload(...)`）與 `to_detail()`。**不要**自己呼叫
   `find_detail_one()` —— 那個方法不會自己加任何條件，忘了補的話會回傳資料表裡的第一筆。
   覆寫的範例見 `modules/users/model.py`；不需要補資料而**刻意不覆寫**的理由寫在
   `modules/roles/model.py`。

## 分頁與篩選列表

`BaseTable`（`apps/api/shared/db/table.py`）提供兩個列表方法，**依「要不要分頁」二選一**：

| 方法 | 回傳形狀 | 對應的回應型別 | 用在 |
|---|---|---|---|
| `get_page(limit=…)` | `{list_data, next_cursor, prev_cursor, has_next, has_previous, total_count}` | `PaginatedResponse[T]` | 資料量會成長的列表 |
| `get_all()` | `{list_data, count}` | `SimpleListResponse[T]` | 天然有限的完整清單（例如下拉選單選項） |

兩者刻意分開、而不是共用一個 `limit: int | None`：合併的話同一個方法會依參數回傳兩種不同形狀，
而路由的 `response_model` 只能標其中一種。需要非分頁清單時請開一條獨立路由
（範例：`GET /roles/options`）。

`get_page` 的主要參數：

| 參數 | 說明 |
|---|---|
| `limit` | 每頁筆數（必填） |
| `cursor` | base64 編碼的 `[sort_value, row_id]` JSON；解碼失敗會拋出 `PaginationError.INVALID_CURSOR`（400） |
| `direction` | `"next"` 或 `"prev"` |
| `sort_field` | 排序欄位，預設 `"created_at"`。排序鍵實際上是 `(sort_field, id)`，`id` 是同值時的 tie-breaker |
| `where` | 篩選條件（SQLAlchemy 運算式的 list）。它**會影響筆數**，所以同時套用在資料查詢與 `total_count` 的 `COUNT(*)` 上。游標條件刻意不進 `COUNT(*)`，否則總數會隨翻頁一直變小 |

補關聯資料**不走參數**，而是覆寫 model 的 `detail_loaders()` 與 `to_detail()`：
`selectinload` 只對這一頁實際取回的列另發一次查詢，成本不隨候選筆數成長。
`to_detail()` 可以自由改寫回傳欄位、甚至把 `id` 換成關聯對象的 id；游標的鍵取自
**ORM 實例**而不是回傳的 dict，因此不受影響。

實作範例見 `apps/api/modules/users/model.py` 的 `find_list()`：「會影響筆數」的篩選放
`where`，「只補欄位」的關聯載入（由角色展開 `permissions`）走 `detail_loaders()`。
`modules/items/` 是第二個可參考的實作（它載入的是建立者暱稱）。

前端側由 `apps/web/shared/pagination/fetch.server.ts` 的 `fetchPaginatedList()` 統一處理，
分頁 UI 與篩選表單分別用 `shared/ui` 的 `Pagination` 與
`shared/ui/patterns/FilterDialog.tsx`。

需要「多個步驟要嘛全部成功、要嘛全部不生效」的寫入時，用
`apps/api/shared/db/transaction.py` 的 `transaction()` context manager 包住這些步驟，
並把 `session` 一路傳給各 model 方法。不需要取得任何 client —— 連線由
`shared/db/session.py` 的 ContextVar 提供（HTTP 請求由 middleware 開好，
WebSocket 與 CLI 自己用 `session_scope()`）。

注意：交易解決的是「多個寫入要一起成功或一起失敗」，**不能**用來防止「兩個請求各自新增一筆
不同的資料而產生邏輯上的重複」；那要靠唯一約束。

## 呼叫 API

前端的 entity 型別由後端 OpenAPI 產生，**不需要（也不能）自己指定回應型別 —— 一切由 `url` 推導**。
產生流程與為什麼契約要進版控見 [`../contracts/README.md`](../contracts/README.md)。

```ts
const res = await apiGet({ url: "/roles/{id}", params: { id } })
if (res.status === "success") res.data.name   // ← 已窄化成 RoleInfo
else res.data.detail                          // ← 已窄化成錯誤形狀
```

路徑寫成**模板**（`/roles/{id}` + `params`），而不是樣板字串（`` `/roles/${id}` ``）。
這是型別能運作的前提：url 必須是字面值，型別系統才知道它對應哪個端點。

以下每一種寫錯的方式都會在 `tsc` 階段失敗：

| 寫錯的方式 | 結果 |
|---|---|
| 端點不存在（`/rolez/`） | 編譯錯誤，且會提示 `Did you mean '/roles/'?` |
| 用了該路徑不支援的方法 | 編譯錯誤 |
| 漏傳路徑參數 | 編譯錯誤（`params` 是必填） |
| request body 少必填欄位、或多了不存在的欄位 | 編譯錯誤 |
| 對沒有 body 的端點傳 `data` | 編譯錯誤 |
| 把回應當成別的 entity 讀 | 編譯錯誤 |

Server Action 的 payload 型別同樣從後端 schema 衍生，不要手寫：

```ts
export async function updateRole(id: string, data: ApiRequestBody<"/roles/{id}", "patch">) {
  return apiPatch({ url: "/roles/{id}", params: { id }, data, refresh: refreshRoles })
}
```

**會收到密碼或註冊金鑰的 action 改收 `FormData`**（目前是登入、註冊、建立使用者、重設密碼）：
Next 的 development action log 會展開一般參數，`FormData` 不會。用
`shared/api/action-form-data.ts` 的 `createActionFormData()` 組、`getActionFormString()` 讀，
簽章收 `ActionFormData<T>` —— `T` 仍然是上面那個從 schema 衍生的型別，欄位名打錯一樣是編譯錯誤。
不是敏感欄位就維持具名參數，不要為了統一而全部換過去。

這套推導沒有執行期行為，唯一值得測的性質是「擋不擋得住錯誤用法」，所以守門測試放在
`tests/shared/api/contract.test-d.ts` —— 它不會被執行，靠 `tsc` 檢查，
並用 `@ts-expect-error` 讓「契約被放寬」與「契約被弄壞」兩個方向都會讓 CI 紅燈。

各模組的 `types.ts` 只放該畫面專屬的型別（篩選條件、表單值），entity 一律從
`@/shared/api/entities` 匯入。

## 新增 Permission

`Permission` 是刻意中央化的靜態 enum（理由見 [`architecture.md`](architecture.md)）：

```python
# apps/api/app/permissions.py
class Permission(BasePermission):
    ALL = "*"
    USER_READ = "users:read"
    USER_UPDATE_OWN = "users:update:own"
    USER_MANAGE = "users:manage"
    PRODUCT_CREATE = "products:create"   # 新增這行
```

label、dependencies 與 assignable metadata 放在擁有此權限的
`modules/<name>/permissions.py`，再由該模組的 manifest 註冊。registry 啟動時會驗證每個 enum
（`ALL` 除外）恰好有一份 metadata；漏掉或重複都會直接啟動失敗。

跑完 `make gen-types` 後前端的 `Permission` 型別會自動同步，不需要手抄一份。

但**前端有一處要跟著加**：`modules/roles/constants.ts` 的 `PERMISSION_ACTION_LABELS`
是 `satisfies Record<PermissionValue, LocaleText>` 的窮盡標籤表，少一個 key 會編譯失敗。
這是刻意的（理由見該檔註解：換成字典就綁不住聯集，畫面會靜靜顯示 `products:create` 原始字串）。
`assignable=False` 的權限不會被渲染，但仍要列進去以滿足窮盡檢查。
需要新的分類標題時，同檔的 `CATEGORY_LAYOUT` 也加一項；不加的話該權限會落到「其他」。

## 新增 WebSocket 事件

WS 模組已列在前後端啟用 registry，連線、ticket 換發與前端重連都在跑；`items` 範例模組
會在建立項目時送出事件。完整範例見 `apps/api/modules/items/service.py` 的 `create_item()`
（含「通知失敗不該讓主要操作失敗」的處理）。

WS 訊息與 REST 一樣走型別契約，唯一來源是 `apps/api/modules/realtime/schema.py` 的 `WsEventType`：

1. 在 `WsEventType` 加一個成員
2. 在送出事件的 service 用 `WsEvent(type=WsEventType.XXX, ...)` 建構（不要寫裸 dict）；
   `WsEvent`、`WsEventType` 與 `ws_manager` 都從 `modules.realtime.public` 匯入
3. `make gen-types`
4. 在該功能自己的 `realtime.ts` 補上對應的畫面反應，並確認它有被
   `config/realtime/handlers.ts` 的 `EVENT_HANDLERS` 展開進來

處理表**依功能分檔**：通用事件在 `shared/realtime/events.ts`，範例模組在
`modules/items/realtime.ts`，由 `config/realtime/handlers.ts` 合併成一張完整的表。
這樣共用殼層不需要認識任何 domain，功能整包刪除時處理也跟著走。
每筆處理有兩個欄位：`toast`（要顯示的提示）與選填的 `onReceive`（該事件專屬的副作用，
例如通知列表重新抓資料）。

第 4 步**忘了做會編譯失敗** —— 合併後的 `EVENT_HANDLERS` 標註為 `Record<WsEventType, …>`
（完整聯集），少一個 key `tsc` 就會指名說少了哪一個。反過來後端刪掉事件、前端沒刪也一樣會失敗。

WS 訊息的信封型別（`WsEvent` 的欄位）手寫在 `shared/api/entities.ts`，不是產生的 ——
FastAPI 只把「有端點回傳」的 model 放進 OpenAPI，而 WS 訊息不經過 HTTP 回應。
改 `WsEvent` 的欄位時要一併更新（`type` 那一半仍由契約保證），
**漏了會被 `tests/shared/api/ws-event-contract.test.ts` 擋下來**（它比對兩邊的欄位名；
型別仍然靠人）。

`GET /ws/events` 會列出所有事件型別；它的用途和 `GET /permissions/` 一樣 ——
把後端 enum 攤到 OpenAPI 上讓型別能被產生出來，同時也是 WS 的自我描述文件。

## 使用 Web Push 推播

和 WS 一樣已由 registry 啟用：訂閱流程（`PushNotificationManager` + service worker）、
訂閱儲存（`modules/push/model.py`）與發送（`modules/push/dispatcher.py`）都已接好。

```python
from modules.push.public import NotificationDispatcher, NotificationPayload

# 推給單一使用者的所有訂閱裝置
await NotificationDispatcher.send_to_user(
    user_id,
    NotificationPayload(title="標題", body="內容", url="/users"),
)

# 推給所有訂閱者
await NotificationDispatcher.broadcast(NotificationPayload(title="公告", body="…", url="/"))
```

`POST /api/push/send`（需要 `push:send` 權限）是現成的廣播端點。只想確認自己這台裝置
有沒有訂閱成功的話用 `POST /api/push/test` —— 它只推給呼叫者自己，任何登入者都能用。

送出失敗只會記錄而不會讓請求失敗；收到 404/410 代表訂閱已失效，會自動刪除該筆訂閱。
未設定 `VAPID_PRIVATE_KEY` 時發送端會靜默略過推播（見 `app/config.py`）；
不過 Docker Compose 把三個 VAPID 變數都設為必填，所以走 `make dev`／`make prod` 一定有值，
`make init` 會自動產生。

## 資料庫 migration

資料結構的一次性變更放在 `apps/api/scripts/migrations/NNNN_描述.py`，每支匯出
`async def migrate(connection) -> str`（`connection` 是 SQLAlchemy 的 `AsyncConnection`）。
已套用的版本記錄在 `_migrations` 資料表，重複執行不會重跑。

**什麼時候需要寫。** 新增一整張資料表不用 —— `make migrate` 會先依 model 定義補上還不
存在的表與索引（`create_missing_tables()`）。但**改既有的表一定要寫**：新增／刪除欄位、
改型別、改索引、改約束、回填資料。`create_all` 只新增、不修改，所以少了 migration 那些
變更完全不會發生，而服務會照常啟動，直到第一次讀寫那個欄位才炸。

**起手式**：複製範本，改成有意義的檔名。

```bash
cd apps/api/scripts/migrations
cp _example.py 0001_add_item_category.py
```

`_example.py` 是一份**不會被執行**的參考範本（`discover_migrations()` 只撿數字開頭的檔案），
裡面有完整規範與三種常見寫法：新增欄位並補預設值、建立索引、改名資料表。

幾條會咬人的規則（`_example.py` 有完整版）：

- 編號要**零補齊四位**，否則 `0010` 會排在 `0002` 前面。
- 版本號不可重複。以上兩條由 `discover_migrations()` 強制檢查，不符合會直接失敗而不是被略過。
- migration 必須**可以重複執行**，因為失敗時不會留下已套用的記號。
- 不要 import model —— migration 的對象常常是已經改掉或即將刪掉的舊結構，綁上目前的
  model 只會讓它跑不起來。用 `text()` 直接下 SQL。
- **不要自己開交易，也不要 `COMMIT`。** 整批 migration 由 `scripts/db.py migrate` 包在
  一個交易裡，任何一支失敗就整批回滾；自己切開交易邊界會讓那個保證失效。
- DDL 一律帶 `IF EXISTS` / `IF NOT EXISTS`，資料更新一律先檢查當前狀態。
- **不要用 `CREATE INDEX CONCURRENTLY`** —— 它不能在交易裡跑。資料量大到不能鎖表時，
  請把那次索引建立當成一次獨立的維運操作。
- migration 必須讓**上一版的程式碼**仍然跑得起來，理由見下面那段。

**上一版那條的理由是回滾。** `deploy.yml` 部署失敗時會自動回滾，
而它退的只有 image 與工作樹 —— **migration 不會跟著退**（沒有 down migration，
失敗時也不留記號）。回滾之後的線上狀態因此是「舊程式碼配新結構」，
那個組合活不活得下來，完全取決於這次的 migration 怎麼寫：

| 這樣寫 | 回滾之後 |
|---|---|
| 加欄位、加索引、補預設值 | 活得下來 —— 舊程式碼看不到新欄位，也不需要看到 |
| 當場改名或刪掉欄位、刪索引 | **死**。舊程式碼還在讀那個名字 |

所以改名與刪除要拆成兩次發版：先加上新的、兩邊並存，確定不會再回滾了，下一版才刪掉舊的。
多一次發版換到的是 `deploy.yml` 那個自動回滾**每次都有用**，
而不是只在剛好沒動結構的那幾次有用。

**不要把資料回填寫進 `app/server.py` 的 lifespan** —— 那會讓每次啟動都做一次全表掃描，
啟動時間隨資料量成長。Seed（初始資料）才屬於 lifespan，回填屬於 migration。

migration 在部署時自動執行，不需要手動介入；執行時機與 `make migrate` 的用法見
[`operations.md`](operations.md#資料庫-migration-何時執行)。

## 初始資料（Seed）

初始資料定義在 model class 上（不是放檔案到某個目錄），由 `BaseTable.ensure_seed()`
依兩個 class variable 決定行為：

| class variable | 說明 |
|---|---|
| `seed_data` | 初始資料的 `list[dict]` |
| `seed_match_key` | upsert 的比對欄位。**有設**：每次都逐筆依此欄位 `INSERT … ON CONFLICT DO UPDATE`（該欄位**必須有唯一約束**，否則 PostgreSQL 無從判斷衝突）；**沒設**：只在資料表完全空的時候才整批 insert |
| `prepare_seed_item()` | 選用的 async classmethod，寫入前轉換資料（例如雜湊密碼） |

`RoleTable` 設了 `seed_match_key = "code"`，所以超級管理者角色**每次啟動都會 upsert** ——
這是刻意的：**日後新增的權限要能補到已經跑起來的環境**（既有的角色列是舊的，
只靠 `create_all` 補不到它）。若你的 seed 不希望被覆寫，就不要設 `seed_match_key`。

執行時機：服務啟動的 lifespan，以及 `python scripts/db.py seed`。兩者都是對
`app/registry.py` 的 `TABLE_MODELS` 逐一呼叫；該清單由每個模組 manifest 的 `tables`
明確聚合，新增 model 時必須註冊。

## 更換 UI 主題

模板只有一份主題（`default`，深色的灰／靛藍）。**只想換色調**就改
`apps/web/app/themes/default.css` 的右手邊，名字不要動。

多加一份主題、導入外部 Design System 與 token 分層，見
[`design-system.md`](design-system.md)。

## 語系（i18n）

模板支援中文與英文，**前後端同一個語系**。沒有引入 i18n 框架，機制自己寫在
`apps/web/shared/i18n/`（六個檔、不到 300 行）—— 兩種語言不需要複數規則與日期格式化，
引入框架付出的相依與慣例衝突大於收益。要做第三種語言以外的需求時再重新評估。

### 語系怎麼決定

1. 首次進站時 `apps/web/proxy.ts` 依 `Accept-Language` 猜一次，寫進 `locale` cookie。
2. 之後**一律以 cookie 為準**。使用者可以在系統設定頁切換（`setLocale` Server Action）。
3. 每個 API 請求都會帶上 `Accept-Language: <locale>`（`shared/api/request.server.ts`），
   所以後端的錯誤訊息與權限標籤跟 UI 是同一種語言。

前端 `resolveLocale()` 與後端 `resolve_language()` 的行為刻意一致（只做前綴比對、
不處理 q 權重）。兩邊分開改的話會出現「UI 是中文但錯誤訊息是英文」這種難重現的錯。

### 新增一個畫面字串

字串住在**擁有它的那一層**的 `i18n.ts`，沒有全站字典：

| 字串屬於 | 放哪裡 |
|---|---|
| 某個模組 | `modules/<name>/i18n.ts`（模組內用相對路徑引用） |
| UI kit | `shared/ui/i18n.ts`（不從 `shared/ui/index.ts` 匯出，它是實作細節） |
| `shared/` 的其他部分 | `shared/i18n/messages.ts` |
| 應用外殼、首頁、錯誤頁、404 | `config/i18n.ts` |

`shared/` 不可以引用 `modules/`，所以中央字典在這個架構下根本組不出來；
就算組得出來，刪掉一個模組時也得回頭清理 shared。

```typescript
// modules/foo/i18n.ts
import { defineMessages } from "@/shared/i18n/dictionary"

export const fooMessages = defineMessages({
  zh: { title: "標題", greet: "你好，{name}" },
  en: { title: "Title", greet: "Hello, {name}" },
})
```

**漏翻譯會編譯失敗**：`en` 的型別是從 `zh` 推導出來的 `Record<keyof zh, string>`，
少一個 key 是型別錯誤、多一個 key 被 excess property check 擋下。

取用的方式依元件種類：

```typescript
// Server Component
const t = await getT(fooMessages)          // @/shared/i18n/locale.server

// client component
const t = useT(fooMessages)                // @/shared/i18n/context

// 純函式（不能用 hook）：收 locale 當參數，呼叫端傳 useLocale()
export function validate(value: string, locale: Locale) {
  const t = translate(fooMessages, locale) // @/shared/i18n/dictionary
}
```

插值寫 `{name}`：`t("greet", { name })`。沒給值的佔位符會原樣留著（替換成空字串的話，
畫面上看起來像文案本來就少一段，很難發現漏傳參數）。

### 三個不走字典的地方

- **導覽列的模組名稱**：`manifest.ts` 的 `label` 是 `LocaleText`（`{ zh, en }`）。
  manifest 必須保持 edge-safe（`proxy.ts` 會經由 `config/routes.ts` 載入它），
  而查字典要的 React context 在那一層不存在。
- **權限標籤**：`modules/roles/constants.ts` 的 `PERMISSION_ACTION_LABELS` 也是 `LocaleText`，
  因為它的 key 綁著 `PermissionValue` 聯集 —— 換成字典就會失去「後端新增權限而前端沒補
  標籤會編譯失敗」這個保護。
- **頁面標題**：用 `export async function generateMetadata()` 而不是靜態的
  `export const metadata`，否則拿不到語系；route adapter 也要跟著轉出 `generateMetadata`。

### 後端

錯誤訊息與權限顯示名稱都用 `shared/http/errors.py` 的 `LangText(zh=…, en=…)` 定義。
`LangException` 會自動依 `current_language` ContextVar 取字（middleware 在
`app/server.py` 依 `Accept-Language` 設定）。不能丟 `LangException` 的地方
（pydantic validator 必須丟 `ValueError` 才會轉成 422）改用 `resolve_text()`，
例見 `shared/http/schema.py` 與 `modules/users/schema.py`。

FastAPI/Pydantic **內建**的 422 訊息仍是框架的英文預設值。要中文化的話，得在
`app/server.py` 的 `RequestValidationError` handler 裡對 `exc.errors()` 的 `type` 做對應表 ——
目前刻意沒做，因為那份對應表要跟著 pydantic 版本維護。

### 加第三種語言

**語系清單的唯一來源是後端**的 `Language` enum，經由 `GET /languages/` 進入 OpenAPI，
前端的 `Locale` 從產生的型別衍生。所以從後端開始：

1. 後端 `shared/http/errors.py` 的 `Language` 加一個成員，`LangText` 加對應欄位。
2. 跑 `make gen-types`。
3. `tsc` 會把前端所有要跟上的地方一次列出來 —— `SUPPORTED_LOCALES`、`HTML_LANG`、
   `Messages`（字典型別）、每一份 `i18n.ts`、manifest 的 `label`、`PERMISSION_ACTION_LABELS`。

第 3 步的量正比於字串數 —— 這正是選擇「型別保證的完整字典」而不是「查不到就 fallback」
的代價與價值：漏掉的地方會全部被列出來，而不是在使用者的畫面上變成另一種語言。

前端刻意留了一份執行期陣列（`SUPPORTED_LOCALES`），因為型別在執行期不存在而 proxy 的比對與
設定頁的下拉需要真的能迭代的值。它與後端的一致由 `satisfies` 加
`tests/shared/i18n/locale.test-d.ts` 的**雙向**可指派性斷言擋著。

### 後端也要記得：不是錯誤的文字一樣要雙語

`LangException` 會自動處理錯誤訊息，但**送到使用者眼前的其他文字**——
WebSocket 事件的 `message`、推播通知的標題與內文——不會經過它。
這類文字用模組層級的 `LangText` 常數加 `resolve_text()`，例見 `modules/push/router.py`
與 `modules/items/service.py` 的 `ITEM_CREATED_MESSAGE`。
這條規則由 `tests/test_i18n_text_usage.py` 的靜態檢查守著（禁止對這兩個欄位直接傳
字面字串或 f-string），同 `Permission`／`WsEventType`／`Language` 那幾份中央清單。

判準只有一條：**`resolve_text()` 取的是「這次請求」的語系，所以收件人必須就是發起請求的人。**

| 情況 | 作法 |
|---|---|
| 只推給呼叫者自己（`send_to_user(current_user_id, …)`） | `resolve_text()`，正確 |
| 廣播給多人 | **不能用** —— 收件人各有各的語系，而事件只組一次 |
| 廣播且內容是管理者自己打的字（`SYSTEM_ANNOUNCEMENT`） | 原樣送，本來就不需要翻譯 |
| 廣播且內容是模板文案 | 事件只帶 type + id，讓每個前端用當地語系自己組 |

角色名稱是**資料不是文案**（存在 DB、使用者可編輯），所以不走這條路。模板 seed 出來的系統
角色由前端依 `role.code` 換成字典文字（`modules/roles/constants.ts` 的
`getRoleDisplayName`），認不出的 code 退回 DB 名稱。

## 改完之後

改過任何後端 schema、權限或 WS 事件之後都要跑：

```bash
make gen-types   # 更新 contracts/openapi.json 與前端型別
make check       # lint + typecheck + test + build
```

`make gen-types` 忘了跑的話，CI 的 `api-types-up-to-date` job 會紅燈，而且前端拿到的是舊型別 ——
錯誤會從編譯期延到執行期。兩份產出（`contracts/openapi.json` 與
`apps/web/shared/api/generated/schema.d.ts`）都要一起 commit。

只想快速確認依賴邊界：`cd apps/web && npm run check:architecture`。
