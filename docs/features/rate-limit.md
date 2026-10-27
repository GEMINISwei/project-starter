# 限流

登入與改密碼有次數上限，每一層都是 5 分鐘內的滑動視窗：

| 操作 | 以什麼計數 | 上限 | 成功後 |
|---|---|---|---|
| 登入 | 用戶端 IP + 帳號 | 10 次 | 歸零 |
| 登入 | 用戶端 IP | 50 次 | **不歸零** |
| 改密碼 | 使用者 | 10 次 | 歸零 |

## 為什麼分兩層

- 只看 IP 會讓同一間辦公室互相影響，只看帳號則可以被拿來鎖定別人，所以第一層用兩者的組合。
- 第一層換個帳號名就是新的額度，擋不住「同一個來源對整份帳號清單各試幾次」，所以另有只看 IP 的
  第二層。它的上限訂得寬，讓同一個 NAT 後面的整間辦公室能正常登入；成功也不歸零，否則用自己的
  帳號登入一次就能把額度洗回來。
- 用戶端 IP 取自 `X-Real-IP`，主機那層沒有正確轉送時所有人共用同一份額度（見
  [`operations.md`](../operations.md#用戶端-ip-與限流)）。
- 計數放在行程記憶體，不用 Redis，見 [ADR 0005](../decisions/0005-in-process-rate-limit.md)。

## 程式與測試

- 機制：[`shared/http/rate_limit.py`](../../apps/api/shared/http/rate_limit.py)、
  [`test_rate_limit.py`](../../apps/api/tests/shared/http/test_rate_limit.py)
- 上限的數字：[`modules/users/router.py`](../../apps/api/modules/users/router.py)
