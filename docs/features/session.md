# Session

登入狀態怎麼撤銷、為什麼不會續期。為什麼不採用 refresh token 見 [ADR 0001](../decisions/0001-revoke-sessions-by-auth-version.md)。

## 撤銷

每個使用者在 `users` 資料表有自己的 `auth_version`，token 簽發時帶著當下的值，每個請求都會跟資料庫比對，
對不上就要重新登入。所以撤銷就是把 `auth_version` +1，**不用重啟、也不用改 `.env`**：

| 怎麼觸發 | 作用範圍 |
|---|---|
| 換密碼（管理者重設或自己改）、登出 | **單一使用者**，自動 +1 |
| `make db revoke-sessions`（見 [`operations.md`](../operations.md#讓所有人登出)） | **所有人**，每個人各 +1 |

單一使用者的 +1 只影響那一個帳號，其他使用者的 token 照常有效：

- 使用者自己改密碼：其他裝置全部登出，這一台會拿到新 token 繼續用。
- 管理者重設密碼：那個人的所有裝置都登出。
- 登出：這個帳號的**所有裝置**一起登出，不只是按下登出的那一台。token 是無狀態的，只刪
  cookie 的話，已經被複製出去的 token 到期前仍然有效，所以登出走的是同一條撤銷路徑。

全員撤銷只用在緊急情況（帳號被盜、懷疑 token 外流）。撤銷本身只是一條 UPDATE，平常的請求也沒有多一次查詢，
負擔在之後**所有人同時重新登入**：

- 每次登入都要算一次 bcrypt，api 是單一行程，人多時登入會排隊變慢。
- 同一個 IP 的登入 5 分鐘內上限 50 次（見〈[限流](rate-limit.md)〉）：同一個 NAT 後面超過 50 人時，
  晚到的要等額度回來才登入得了。

撤銷擋不住金鑰外洩：拿到 `JWT_SECRET_KEY` 的人可以自己簽一張帶任何世代的 token。金鑰外洩時要換掉
`JWT_SECRET_KEY` 本身，舊 token 會跟著全部失效（見 [`operations.md`](../operations.md#更換-jwt_secret_key)）。

## 不會續期

沒有 refresh token，也沒有「有在操作就延長」。`EXPIRE_HOURS` 是**登入後多久一定要重新登入**
的硬上限，跟有沒有在用無關 —— 設 8 小時的話，早上九點登入的人下午五點會被導回登入頁。

## 程式與測試

- token 的簽發與比對：[`shared/auth/tokens.py`](../../apps/api/shared/auth/tokens.py)、
  [`shared/auth/dependency.py`](../../apps/api/shared/auth/dependency.py)、
  [`test_tokens.py`](../../apps/api/tests/shared/auth/test_tokens.py)
- 改密碼與登出時 +1：[`modules/users/account.py`](../../apps/api/modules/users/account.py)、
  [`test_password_revocation.py`](../../apps/api/tests/modules/users/test_password_revocation.py)
