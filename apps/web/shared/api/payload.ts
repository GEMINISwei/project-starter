// `shared/api/request.server.ts` 的純資料轉換部分，抽出來放在沒有 `server-only` 的模組裡：
// request.server.ts 本身是 I/O 外殼（cookie、fetch、redirect、revalidate），在單元測試裡載入不了；
// 而這兩個函式是純函式，正是最容易寫錯、也最值得測的部分。

import type { DataObject } from "@/shared/api/contract"

/**
 * 過濾要送出的 body。
 *
 * 只濾掉 `undefined`，**不濾空字串** —— 空字串是有意義的值。把它濾掉會讓使用者永遠無法
 * 清空一個欄位（送出的 payload 裡不會有那個 key，後端的 $set 就不會動到它）。
 * 呼叫端若真的想省略某個欄位，請明確傳 `undefined`。
 */
export function getBodyData(data: DataObject): DataObject {
  return Object.fromEntries(
    Object.entries(data).filter(([, value]) => value !== undefined)
  )
}

export type ParsedErrorDetail = {
  message: string
  fieldErrors?: Record<string, string>
}

/**
 * 解析後端回傳的 `detail`。
 *
 * FastAPI 的 422 是 `detail: [{loc, msg, ...}]`；業務錯誤則是字串。陣列要保留每個欄位的
 * 細節，讓表單能把錯誤交給對應輸入框，而不是只留下第一句訊息。
 */
export function parseErrorDetail(detail: unknown): ParsedErrorDetail {
  if (typeof detail === "string" && detail) {
    return { message: detail }
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const fieldErrors = collectFieldErrors(detail)
    const messages = Object.entries(fieldErrors).map(([field, msg]) => `${field}: ${msg}`)
    if (messages.length > 0) {
      return { message: messages.join("；"), fieldErrors }
    }
  }

  return { message: "Server Unknown Error" }
}

/**
 * 從 FastAPI 的 `detail` 陣列取出「欄位 → 訊息」；認不出形狀的項目直接略過。
 *
 * key 只取 `loc` 的**最後一段**：開頭那段是位置前綴（`body`／`query`／`path`），留著會逼
 * 呼叫端反推前綴與分隔字元（沒有檢查器守著，改掉就讓所有欄位錯誤安靜地對不上），也會漏進
 * `message` 變成使用者看得到的 `body → password: …`。
 *
 * 代價：巢狀 body 有同名欄位時後者會覆蓋前者。這個模板的 request body 都是平的，真的出現
 * 巢狀時再改成把 `loc` 陣列一起帶出去。
 */
function collectFieldErrors(detail: unknown[]): Record<string, string> {
  const fieldErrors: Record<string, string> = {}

  for (const item of detail) {
    if (typeof item !== "object" || item === null) continue
    const entry = item as { loc?: unknown[]; msg?: unknown }
    const loc = Array.isArray(entry.loc) ? entry.loc.map(String) : []
    const field = loc.at(-1) ?? ""
    const msg = typeof entry.msg === "string" ? entry.msg : ""
    if (field && msg) fieldErrors[field] = msg
  }

  return fieldErrors
}
