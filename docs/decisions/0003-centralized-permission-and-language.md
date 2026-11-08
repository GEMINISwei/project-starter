# 0003. `Permission` 與 `Language` 集中定義，不由模組動態組裝

狀態：採用（2026-10-25）

## 背景

模組化的原則是新增功能不改共用檔案，照理權限與語言應由模組啟動時註冊。但動態註冊的值在 OpenAPI 裡只是
`string`，前端拿不到可檢查的型別。

## 決定

`app/permissions.py` 的 `Permission` 與 `shared/http/errors.py` 的 `Language` 是 enum，集中定義。
這是**僅有的兩處**新增功能要改共用檔案的地方。

## 後果

- 進 OpenAPI 是字串聯集，前端打錯權限名稱 `tsc` 會失敗。
- 新增或刪除模組時要記得改 enum。
- 權限的顯示標籤與分類仍跟著模組（`PermissionSpec`）。

規則見 [`architecture.md`](../architecture.md#兩份刻意中央化的清單)。
