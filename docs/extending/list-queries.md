# 分頁、篩選與交易

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
