# 0007. 不內建錯誤追蹤與告警

狀態：採用（2026-10-25）

## 背景

正式環境常接錯誤追蹤（Sentry）、結構化 log、指標與告警。做法依部署平台而定，錯誤內容又可能帶著使用者資料，
送不送第三方是專案自己的決定。

## 決定

只提供寫到 stdout 的請求紀錄、貫穿三個服務的 request id 與 Docker healthcheck。看 log 用 `make services logs`。

## 後果

- 不綁第三方，也不把使用者資料送出去。
- 出錯沒人收到通知；瀏覽器端的錯誤在主機上完全看不到；重建容器時舊 log 消失。
- 上線給外部使用者或需要主動發現錯誤時，先補錯誤追蹤（Sentry 或相容的自架 GlitchTip）。

現況見 [`operations.md`](../operations.md#可觀測性只到-stdout)。
