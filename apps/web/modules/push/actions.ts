"use server"

import { apiDelete, apiPost } from "@/shared/api/request.server"
import type { ApiRequestBody } from "@/shared/api/contract"

// 訂閱的註冊／退訂走具名 Server Action，與其他模組一致（見 `modules/items/actions.ts`）。
//
// **不要改成從瀏覽器直接 `fetch("/api/push/subscriptions")`。** 那樣路徑與欄位名都是
// 手寫字串：後端 `modules/push/schema.py` 改一個欄位，前端不會編譯失敗，只會在使用者
// 按下「開啟通知」時安靜失敗 —— 而 `client.ts` 的錯誤一律只 console.warn，沒有人會發現。
// 走這一層，路徑、payload 與回應形狀都由 OpenAPI 契約推導。

export async function registerPushSubscription(
  data: ApiRequestBody<"/push/subscriptions", "post">,
) {
  return apiPost({ url: "/push/subscriptions", data })
}

export async function removePushSubscription(endpoint: string) {
  return apiDelete({ url: "/push/subscriptions", query: { endpoint } })
}
