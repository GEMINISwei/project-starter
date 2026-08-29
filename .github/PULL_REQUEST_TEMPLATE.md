<!--
這份模板是「功能級規格」的落點，理由見 docs/development.md 的「規格與測試的三層」。

**開始寫程式之前就要填**：開分支、推一個空 commit、開 draft PR，先把下面「這個 PR 做什麼」
與「驗收條件」兩段寫完 —— 那一層的價值就在動手之前，落點晚於動手等於沒有落點。
其餘段落等做完再補。步驟見 docs/development.md 的「落點要在動手之前存在」。

用不到的段落整段刪掉，不要留著空標題。
-->

## 這個 PR 做什麼

<!-- 一到三句。為什麼要做，寫在這裡；怎麼做，看 diff。 -->

## 驗收條件

<!--
一條一行，用「什麼情況下、做了什麼、應該怎樣」的自然語言寫（不是 Gherkin，不必寫
Given/When/Then），**每一條後面接一行「→ 測試名稱」，名稱用反引號包起來**：

- 沒有 items 讀取權限的使用者打 GET /api/items/ 會拿到 403
  → `test_get_items_without_permission_returns_403`
- 列表沒有任何資料時，分頁仍然顯示「共 1 頁」而不是空白
  → `"沒有資料時分頁顯示共 1 頁"`

`make check-acceptance` 會確認那個名稱在 apps/*/tests/ 底下真的存在。寫不出測試名稱，
代表那一條還沒被想清楚 —— 那就是動手之前要問掉的地方。

**那個 job 在 draft 上不跑**，所以 draft 期間要看紅綠燈就自己跑 `make check-acceptance`；
按下 Ready for review 的那一刻 CI 會真的驗一次。

純文件、CI 調整那類沒有行為變更的改動，在 PR 標題加上 [skip acceptance]。
-->

-

## 改動到既有測試

<!--
**只在這個 PR 改動或刪掉了既有的測試時才留著這一段**，純新增測試不必寫。

寫明**原本那個斷言為什麼是錯的**（介面改名、相依升級換掉 mock、那一條從一開始就寫錯）。
`make check-test-edits` 會攔下沒有說明的改動 —— 它沒有逃生門，因為說明本身就是逃生門。
改實作讓測試變紅、再把測試改成會過的樣子，是它要擋的東西。
-->

## 影響到的中央清單

<!-- 動到哪幾份就勾哪幾份；都沒動就整段刪掉。三份清單刻意中央化的理由見 AGENTS.md。 -->

- [ ] `Permission`（`apps/api/app/permissions.py`）
- [ ] `WsEventType`
- [ ] `Language`
- [ ] `ENABLED_MODULES`（前端 `config/routes.ts`、後端 `app/registry.py`，**兩邊都要**）
- [ ] `APP_VERSION` 與 `CHANGELOG.md` 最上面那個版號標題

## 取消 draft 前

<!--
**這一段是 draft → ready 的判準，不是做完之後的回報。** 有一條沒過就代表還在 draft。
最後兩條沒有任何檢查器會提醒，理由見 docs/development.md 的
〈取消 draft 之前：自己讀一次 diff〉。
-->

- [ ] `make check`
- [ ] `make check-acceptance` —— CI 的那個 job 在 draft 上跳過，**本機這次是唯一的紅綠燈**
- [ ] `make gen-types`（動過 schema／權限／WS 事件／語系／`APP_VERSION` 才需要）
- [ ] 動過 `scripts/`、`.env.example`、compose、nginx 模板或 `.md` 時，對應的 `make check-*`
- [ ] **驗收條件描述的仍然是你真的做出來的東西** —— 實作途中改了主意就回頭改它。
      `check-acceptance` 只驗「指得出一個存在的測試」，驗不出那一條已經跟成品對不上
- [ ] **整份 diff 自己讀過一次**（Files 分頁，不是回想自己寫了什麼）
