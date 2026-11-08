# 0001. 用 `auth_version` 撤銷 session，不做 refresh token

狀態：採用（2026-10-25）

## 背景

主流做法是短效 access token 加 refresh token，撤銷靠黑名單或 refresh token 表，要多一套儲存與續期流程。
模板的情境是內部系統，帳號數量有限。

## 決定

- 每個使用者有 `auth_version`，簽進 JWT，每個請求跟資料庫比對，對不上就要重新登入。
- 撤銷就是 +1：改密碼、登出影響單一使用者（所有裝置），`make db revoke-sessions` 影響所有人。
- 不做 refresh token、不續期，`EXPIRE_HOURS` 是硬上限。

## 後果

- 撤銷不用重啟、不用改 `.env`；每個請求本來就查使用者，不多一次查詢。
- 到 `EXPIRE_HOURS` 一定登出，即使正在操作；做不到「只登出這一台」。
- 擋不住 `JWT_SECRET_KEY` 外洩，那時要換金鑰。
- 需要「保持登入」或對外開放時重新檢討。

現在的行為見 [Session](../features/session.md)。
