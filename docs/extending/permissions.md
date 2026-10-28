# 權限

替模組加權限：新增模組時，或替既有模組多開一個動作（例如匯出）時都照這份做。
以 `products` 為例。

## 步驟

1. 在 `apps/api/app/permissions.py` 的 `Permission` enum 加成員（`PRODUCT_READ = "products:read"`）。
   這是刻意中央化的清單，理由見 [`architecture.md`](../architecture.md#兩份刻意中央化的清單)。
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
