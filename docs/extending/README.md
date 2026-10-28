# 擴充指南

用這個模板開新案時，可以加上的擴充項目與做法，一個任務一份。內建功能怎麼運作見
[`features/`](../features/README.md)，依賴邊界與模組介面的**規則**在 [`architecture.md`](../architecture.md)。

範例一律照抄現成模組，兩邊都從 **roles** 開始（標準的 CRUD：列表、建立、修改、停用）：
後端 `apps/api/modules/roles/`、前端 `apps/web/modules/roles/`。需要更進一步的寫法時再參考
users：關聯表與篩選（`model.py`）、依授權模型拆檔（`service.py`／`account.py`／`superuser.py`）。

這裡是操作指南，段落依任務決定，沒有固定模板。新增一份時在下面加一行。

| 文件 | 什麼時候讀 |
|---|---|
| [新增一個功能模組](new-module.md) | 要加一個有 API 與頁面的新功能 |
| [權限](permissions.md) | 新模組要權限，或替既有模組多開一個動作 |
| [Migration](migrations.md) | 改了 model 的欄位、索引、約束，或發版前要整理 migration |
| [分頁、篩選與交易](list-queries.md) | 寫列表 API、補關聯資料、多個寫入要一起成功或失敗 |
| [上傳檔案](uploads.md) | 功能要收圖片、影片或文件，或要決定上傳的大小上限 |
| [呼叫 API](api-client.md) | 前端要打後端、寫 Server Action、命名 entity 型別 |
| [初始資料（Seed）](seed.md) | 資料表要有預設資料，或要改系統角色的定義 |
| [背景工作（尚未內建）](background-jobs.md) | 要寄信、匯出、排程這類不該卡住請求的工作 |
| [語系（i18n）](i18n.md) | 加使用者看得到的字串、後端訊息，或加第三種語言 |
| [更換視覺／導入 Design System](design-system.md) | 要改專案的外觀、導入設計系統 |
