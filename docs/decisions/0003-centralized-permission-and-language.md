# 0003. `Permission` 與 `Language` 集中定義，不由模組動態組裝

狀態：採用（2026-10-25）

## 背景

模組化架構的原則是「新增功能不必改共用檔案」，照這個原則，權限與語言應該由各模組在啟動時註冊。
但動態註冊的值在 OpenAPI 裡只會是 `string`，前端拿不到可以檢查的型別。

## 決定

`app/permissions.py` 的 `Permission` 與 `shared/http/errors.py` 的 `Language` 是 enum，集中在一處定義。
它們是**僅有的兩處**「新增功能要改共用檔案」的地方。

## 後果

- 它們進 OpenAPI 時是字串聯集，前端打錯權限名稱會讓 `tsc` 失敗，不會變成執行期安靜失效。
- 新增模組時要多改一個共用檔案，刪除模組時也要記得移除 enum 成員。
- 權限的顯示標籤與分類仍然跟著模組走（`permissions.py` 的 `PermissionSpec`），不受影響。

規則本身見 [`architecture.md`](../architecture.md#兩份刻意中央化的清單)。
