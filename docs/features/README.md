# 系統功能

功能怎麼運作、為什麼這樣設計，一個主題一份。要執行的指令與救援步驟在 [`operations.md`](../operations.md)，
要加新功能見 [`extending/`](../extending/README.md)。

只寫讀程式碼推不出來的事：刻意的限制、沒做的功能、跨模組的行為與它的代價。欄位與畫面上有什麼，
程式碼與測試已經寫了，不在這裡重複；驗收條件也一樣，寫在 PR 的「驗證」段，合併後由測試名稱保留
（[說明](../testing.md#驗收條件與測試名稱)）。新增一份時複製 [`_template.md`](_template.md)，並在下面加一行。

每份的開頭與結尾是固定的（`apps/api/tests/test_doc_features.py` 會擋）：標題底下先用一段說明涵蓋範圍，
最後一段是「程式與測試」，連到入口檔與至少一個測試。中間的段落依主題命名。

## 平台功能

模板內建，繼承的專案通常不用改。

| 文件 | 什麼時候讀 |
|---|---|
| [帳號、角色與密碼](accounts-roles.md) | 動到建立帳號、角色指派、權限檢查、後台入口、密碼重設 |
| [Session](session.md) | 動到登入、登出、token、`auth_version`、`EXPIRE_HOURS` |
| [限流](rate-limit.md) | 動到登入或改密碼的次數限制、用戶端 IP 的取得 |
| [語系](i18n.md) | 動到 `locale` cookie、`Accept-Language`、後端錯誤訊息的語言 |

## 業務功能

繼承的專案在這裡加上自己的功能。
