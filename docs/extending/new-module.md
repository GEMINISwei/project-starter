# 新增一個功能模組

以 `products` 為例，照順序做。**前後端模組同名。**

## 1. 後端模組

1. 複製 `apps/api/modules/roles/` 為 `modules/products/`，改成自己的 router、schema、service 與
   `ProductTable`。roles 沒有 `permissions.py`（後台只開放給超級管理者），照〈[權限](permissions.md)〉新增。
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

## 2. 權限

照〈[權限](permissions.md)〉在 `Permission` enum 加成員，並在 `modules/products/permissions.py`
寫 `PermissionSpec`，再由 manifest 註冊。

## 3. Migration

```bash
make db migration "add products"
```

**產生之後自己讀一遍**，注意事項見〈[Migration 注意事項](migrations.md#注意事項)〉。

## 4. 產生前端型別

```bash
make gen-types
```

`contracts/openapi.json` 與 `apps/web/shared/api/generated/schema.d.ts` 兩份都要 commit。
前端的 `Permission` 型別、端點與 entity 型別都會跟著更新。

## 5. 前端模組

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
   清單見 [`architecture.md`](../architecture.md#frontend-module-介面)。
5. 模組的 server page 自己再用 `canAccessRoute(permissions, PRODUCTS_ROUTE)` 擋一次（引用自己
   manifest 的常數；模組不能引用 `config/`）。layout 只做粗篩，真正的授權在後端。
6. 列表頁直接複用：`shared/pagination` 的 `parsePagination()`、`fetchPaginatedList()`；
   `@/shared/ui` 的 `ListPageHeader`、`ListTableCard`、`TableRow`、`FilterDialog`、`FormDialog`、
   `useListFeedback`、`useActionSubmit`。create／edit 對話框各自一個元件檔。
7. 畫面裡有分支邏輯時抽進 `capabilities.ts`，測試放 `apps/web/tests/modules/products/`。

## 6. 檢查

```bash
make check               # lint + contract + migrate + types + test + build
make check integration   # 需要資料庫的測試 + model 與 migration 一致
make check e2e           # 畫面流程有改時：拋棄式正式環境 + Playwright
```
