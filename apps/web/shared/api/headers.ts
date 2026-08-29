// `shared/api/request.server.ts` 的 header 組裝。抽成獨立模組的判準同 `shared/api/payload.ts`。
//
// 這裡抽出來的**主要理由是 `Accept-Language`**：那一個 header 是後端雙語能力的唯一開關，
// 漏掉的話後端一律回預設語系 —— 前端切到任何語言都看起來「正常」，只是訊息永遠是中文。
// 這種錯誤沒有任何執行期徵兆，所以它必須是能被測試釘住的。

import type { Locale } from "@/shared/i18n/locale"

export type RequestHeaderOptions = {
  locale: Locale
  /** 這個端點需不需要身分。`auth: "none"` 的請求即使手上有 token 也不該帶上去。 */
  authRequired: boolean
  token?: string
  contentType?: "json" | "form-data"
  /**
   * 進來這個請求時 nginx 帶上的追蹤識別碼，原樣往後端傳。
   *
   * 少了這一行，correlation id 就在 Next 這一跳斷掉：後端會為每次呼叫自己產一個新的，
   * 而這個架構下**幾乎所有** API 呼叫都是從 Server Component／Server Action 發出的，
   * 等於使用者那一次操作與後端的紀錄永遠對不起來。header 名稱與後端 `app/server.py` 的
   * `REQUEST_ID_HEADER`、nginx 模板三處必須一致。
   */
  requestId?: string
  /**
   * 進來這個請求時 nginx 帶上的用戶端 IP（`X-Real-IP`），原樣往後端傳。
   *
   * **少了這一行，後端的登入／註冊限流就完全失去意義。** 那兩條端點是 Server Action 呼叫的，
   * 由 Next 伺服器端直接連 `api:8000` —— 後端看到的 peer address 是 web 這個容器，全站共用
   * 同一個值。結果是 signup 的限流變成「整個部署每小時 5 次」，而 login 的 key 退化成只剩帳號，
   * 剛好變成它想避免的「可以被拿來惡意鎖定他人」。
   *
   * 轉傳的值是 nginx 以 `$remote_addr` **覆寫**過的（見 infra/nginx/templates/），偽造不了。
   * 後端 `shared/http/rate_limit.py` 的 `client_ip()` 讀同一個 header。
   */
  clientIp?: string
}

const CONTENT_TYPES = {
  "json": "application/json",
  "form-data": "application/x-www-form-urlencoded",
} as const satisfies Record<NonNullable<RequestHeaderOptions["contentType"]>, string>

export function buildRequestHeaders(options: RequestHeaderOptions): Record<string, string> {
  const headers: Record<string, string> = {
    // 後端的錯誤訊息與權限標籤都依這個 header 回應（見 apps/api 的 shared/http/errors.py）。
    "Accept-Language": options.locale,
  }

  // 把 token 放進 Cookie 而不是 Authorization：後端讀的是 cookie（見 shared/auth/dependency.py），
  // 而這一段是 Next 伺服器端對後端的請求，瀏覽器的 cookie 不會自動跟過來。
  if (options.authRequired && options.token) {
    headers["Cookie"] = `access_token=${options.token}`
  }

  if (options.contentType) {
    headers["Content-Type"] = CONTENT_TYPES[options.contentType]
  }

  if (options.requestId) {
    headers["X-Request-ID"] = options.requestId
  }

  if (options.clientIp) {
    headers["X-Real-IP"] = options.clientIp
  }

  return headers
}
