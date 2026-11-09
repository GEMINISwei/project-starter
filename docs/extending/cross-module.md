# 跨模組：用到別的模組的資料或能力

功能要用到別的模組的東西時照這份做。規則與理由在 [`architecture.md`](../architecture.md#模組之間的資料關聯)
與 [starter/0013](../starter/0013-cross-module-references-by-id.md)，檢查會擋的部分見 [`testing.md`](../testing.md#架構本身也有測試)。

範例都取自 users 與 roles：users 參照 roles（使用者身上掛角色），roles 不知道 users 存在。

## 1. 先判斷該不該是兩個模組

| 這樣的關係 → 放同一個模組 | 這樣的關係 → 分開，以 ID 參照 |
|---|---|
| 經常 JOIN、要用對方的欄位排序或篩選 | 只需要顯示對方的名稱 |
| 通常一起改 | 各自演進 |
| 有共同的規則要同時成立（訂單與明細的金額） | 只要求「指到的東西存在」 |
| 一方單獨存在沒有意義 | 各自都有獨立的意義 |

不要看有沒有外鍵：幾乎所有業務資料都參照 users，有外鍵就合併的話最後只剩一個模組。分開之後，如果對方的 public
多到像是把內部原封不動轉出去，就是邊界畫錯了，合併回來。放在同一個模組時，內部可以自由用 ORM relationship、
JOIN 與 `detail_loaders()`，下面的做法都不需要。

## 2. 資料表與外鍵

| 關係 | 做法 | 放在哪個模組 |
|---|---|---|
| 多對一（訂單屬於使用者） | 外鍵欄位 `user_id` | 參照的一方 |
| 多對多（使用者的角色） | 關聯表 | 這個關係有業務意義的一方（`user_roles` 在 users） |
| 一對一擴充（替使用者加帳務資料） | 自己的表，`user_id` 加唯一約束 | 擴充的一方，**不在對方的表加欄位** |
| 歷史、稽核紀錄 | 只存 ID 與當時的快照，**不加外鍵** | 紀錄的一方，原始資料刪掉後紀錄仍要留著 |

外鍵用字串宣告，不 import 對方的資料表：

```python
# modules/users/model.py
Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True)
```

`ondelete` 由持有外鍵的一方選：

| 選項 | 用在 | 使用者看到的 |
|---|---|---|
| `CASCADE` | 關聯表、擴充表：對方不在了，這列也沒有意義 | 一起刪掉 |
| `RESTRICT` | 業務資料（預設）：還有人用就不准刪 | 409「仍有其他資料使用中，無法完成操作」 |
| `SET NULL` | 選填的關聯 | 欄位變成空的 |

寫入時指到不存在的資料，使用者看到 409「參照的資料不存在」。兩種 409 都由平台轉換，模組不必自己攔
`IntegrityError`。

## 3. 後端：讀對方的資料

只 import 對方的 `public.py`，拿到的是函式與它的回傳型別，不是資料表（`public.py` 轉出 ORM 類別或 `Table` 會被
架構測試擋下）。

**提供的一方**在自己的 `model.py` 寫函式，由 `public.py` 轉出：

```python
# modules/roles/model.py
async def find_role_details(role_ids: list[str]) -> list[RoleDetail]:
    return await RoleTable.find_details_by_ids(role_ids)

# modules/roles/public.py
from .model import RoleDetail, expand_permissions, find_role_details, get_super_admin_role_id
```

- 一定要有**批次**版本（收一組 id），呼叫端補一整頁資料時才不會每列查一次。
- 不收 `session`：跨模組的呼叫用目前的 session，自然與呼叫端在同一個交易裡。
- 屬於自己的規則放在這裡，不讓呼叫端各寫一份（停用的角色不給權限是 roles 的 `expand_permissions`）。

**使用的一方**要在列表或單筆裡帶出對方的資料時，覆寫 `to_details()`，一次補完整批：

```python
# modules/users/model.py（節錄）
@override
@classmethod
async def to_details(cls, rows, session):
    assigned = await cls._assigned_role_ids([row.id for row in rows], session)  # 自己的關聯表
    roles = await find_role_details(sorted({rid for ids in assigned.values() for rid in ids}))
    ...
```

`find_detail_*`、`get_all`、`get_page` 都經過 `to_details()`，所以寫一次就涵蓋所有讀取路徑。代價是比 JOIN 多一次
查詢，但次數固定、不隨筆數增加；寫一個測試鎖住查詢次數（例：`tests/modules/users/test_model.py` 的
`test_find_list_query_count_does_not_grow_with_users`）。

篩選只用自己擁有的欄位或關聯表（users 依角色篩選查的是 `user_roles` 的 `EXISTS`，不碰 roles 的表）。

## 4. 後端：對方要通知我

被參照的一方的資料變了，參照者要跟著做事或否決時（停用使用者時取消訂單、刪除前檢查），被參照的一方不能
import 參照者，改用模組事件：它發布、參照者在 manifest 訂閱。做法見〈[模組事件](module-events.md)〉。
只是「還有人用就不准刪」的話，`RESTRICT` 就夠了。

## 5. 前端：用對方的東西

前端一樣只引用對方的 public entry，依用在哪裡分兩個：

| 要用的 | 放在對方的 | 例 |
|---|---|---|
| 讀資料（對方的端點） | `public.server.ts` | users 的頁面用 roles 的 `getRoleOptions()` 取下拉選單，不自己寫 `/roles/options` |
| 畫面規則、字典 | `public.client.ts` | users 的表格用 roles 的 `getRoleDisplayName()` 與 `rolesMessages` 顯示角色名稱 |

```ts
// modules/users/page.server.tsx
import { getRoleOptions } from "@/modules/roles/public.server"

// modules/users/capabilities.ts
import { getRoleDisplayName, type rolesMessages } from "@/modules/roles/public.client"
```

- 端點屬於擁有它的模組：對方改網址時只改它自己的 loader。錯誤訊息由呼叫端決定，文案屬於呼叫端的畫面。
- 「系統角色走字典、其他角色用名稱」這類顯示規則只在擁有它的模組寫一份。
- 型別在**用到它的模組**自己的 `types.ts` 以 `Schema<"RoleInfo">` 命名，不搬進 shared，也不從對方 import
  （[說明](../architecture.md#新增與移除-module)）。
- 後端回應已經內嵌對方的摘要時，前端直接用，不要拿 id 再打一次對方的端點。

## 6. 跨模組的排序與彙總

需要的計算牽涉別的模組時，依序考慮：

| 需求 | 做法 |
|---|---|
| 資料量小，只是把幾個模組的資料拼起來 | 呼叫各模組 public 的批次函式，在程式裡組 |
| 加總、分組，只牽涉一個模組的資料 | 請擁有資料的模組在 public 提供統計函式（例：`summarize_by_month()`），計算在資料庫裡做 |
| 要用對方的欄位排序或篩選再分頁 | 在自己的表存一份**去正規化的副本**（例：訂單存 `customer_name`），對方改名時用[模組事件](module-events.md)同步 |
| 一定要跨模組 JOIN、資料量大 | 由一個模組擁有**唯讀的資料庫 view**，在它的 public 寫明這是例外的理由 |

報表是最常見的例子：報表模組自己不擁有業務資料，依上表向各模組取數字，計算儘量交給擁有資料的模組。

唯讀 view 的寫法：在 migration 裡用 `op.execute("CREATE VIEW ...")` 建立（autogenerate 不會產生 view，要手寫，
`downgrade` 寫對應的 `DROP VIEW`）。擁有它的模組用 Core 的 `Table` 手寫欄位，宣告在**獨立的 `MetaData()`** 上：
放進 `BaseTable.metadata` 的話，autogenerate 會把它當成要建立的資料表，`alembic check` 也會失敗；也不註冊進 manifest
的 `tables`（那是給 seed 用的實體表）。view 依賴的欄位被改名或刪掉時 migration 會失敗，這正是它能當成例外的前提：
耦合是看得見的。
