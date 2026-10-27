// 不要加上 `server-only`: 這是純函式, 抽出來就是為了能被單元測試 (同 cookie-options.ts)。

import type { ApiResponse } from "@/shared/api/contract"

/**
 * 從簽發 token 的回應裡拿掉 `access_token`, 給 Server Action 當回傳值用。
 *
 * Server Action 的回傳值會被序列化送進瀏覽器。token 寫進 httpOnly cookie 之後
 * 若再原樣回傳, 前端 JS (以及任何 XSS) 就讀得到它, httpOnly 形同虛設。
 * 所以凡是會呼叫 `setAccessTokenCookie` 的 action, 回傳前都要經過這裡。
 */
export function withoutAccessToken<T extends { access_token: string }>(
  res: ApiResponse<T>,
): ApiResponse<Omit<T, "access_token">> {
  if (res.status !== "success") return res

  const data: Partial<T> = { ...res.data }
  delete data.access_token

  return { ...res, data: data as Omit<T, "access_token"> }
}
