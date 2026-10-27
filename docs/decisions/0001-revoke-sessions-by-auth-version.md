# 0001. 用 `auth_version` 撤銷 session，不做 refresh token

狀態：採用（2026-10-25）

## 背景

token 是無狀態的 JWT。常見的做法是短效的 access token 加上 refresh token，搭配「有在操作就延長」，
撤銷則靠黑名單或 refresh token 的資料表。這些都要多一套儲存與續期流程，而模板的使用情境是內部系統，
帳號數量有限。

## 決定

- 每個使用者有一個 `auth_version`，簽進 token，每個請求都跟資料庫比對，對不上就要重新登入。
  撤銷就是把它 +1：改密碼、登出影響單一使用者，`make db revoke-sessions` 影響所有人。
- 登出也走同一條路，所以會登出那個帳號的**所有裝置**。只刪 cookie 的話，被複製出去的 token
  到期前仍然有效。
- 不做 refresh token，也不續期。`EXPIRE_HOURS` 是登入後的硬上限。

## 後果

- 撤銷不用重啟、不用改 `.env`，每個請求本來就要查使用者，比對 `auth_version` 不會多一次查詢。
- 使用者在 `EXPIRE_HOURS` 到時一定會被登出，即使正在操作。
- 「只登出這一台」做不到。
- 擋不住 `JWT_SECRET_KEY` 外洩，那時要換金鑰本身。
- 需要「保持登入」或對外開放的產品時要重新檢討。

現在的行為見 [Session](../features/session.md)。
