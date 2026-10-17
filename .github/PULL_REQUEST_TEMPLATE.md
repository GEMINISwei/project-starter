<!-- PR 標題用 Conventional Commits（`feat: add product list page`）：squash merge 後它就是 main 的 commit。
     先開 Draft，「送出前」勾完再按 Ready for review。流程見 docs/development.md#開發流程 -->

## 這個 PR 做什麼

<!-- 一到三句，寫「為什麼」；「怎麼做」看 diff。 -->

## 驗收條件

<!-- 一條一行，後面接測試名稱。寫不出測試名稱，代表那一條還沒想清楚。
- 管理者不能停用自己的帳號 → `test_cannot_disable_self` -->

-

## 送出前

- [ ] `make check`
- [ ] 動過 schema／權限／語系：`make gen-types`
- [ ] 動過 model：`make db migration "說明"`，並跑 `make check integration`
- [ ] 新增模組：前端 `config/routes.ts` 與後端 `app/registry.py` 的 `ENABLED_MODULES` 都加了
- [ ] 整份 diff 自己讀過一次
