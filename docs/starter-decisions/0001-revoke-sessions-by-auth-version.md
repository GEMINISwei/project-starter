# 0001. 用 `auth_version` 撤銷 session，不做 refresh token

現在的行為見 [Session](../features/session.md)。

## 決定

- 每個使用者有 `auth_version`，簽進 JWT，每個請求跟資料庫比對，對不上就要重新登入。
- 撤銷就是 +1：改密碼、登出影響單一使用者（所有裝置），`make db revoke-sessions` 影響所有人。
- 不做 refresh token、不續期，`EXPIRE_HOURS` 是硬上限。

## 為什麼

主流做法是短效 access token 加 refresh token，撤銷靠黑名單或 refresh token 表，要多一套儲存與續期流程。
模板的情境是內部系統，帳號數量有限，不值得多這一套。

每個請求本來就要查使用者，順便比對 `auth_version` 不多一次查詢；撤銷也不用重啟服務或改 `.env`。

## 代價

- 到 `EXPIRE_HOURS` 一定登出，即使正在操作；做不到「只登出這一台」。
- 擋不住 `JWT_SECRET_KEY` 外洩，那時要換金鑰。

## 什麼時候重新檢討

需要「保持登入」、只登出單一裝置，或對外開放給大量使用者時。
