/**
 * Next 伺服器端錯誤的一行紀錄, 由 `instrumentation.ts` 的 `onRequestError` 呼叫。
 *
 * request id 對上 nginx 與 api 的紀錄, digest 對上使用者截圖裡的錯誤代碼 (錯誤畫面顯示的就是它)。
 * 開頭的寫法與 api 的請求紀錄相同 (`LEVEL:` 對齊、UTC 時間), 三層的 log 看起來是同一種格式。
 */

type ErrorRequest = {
  readonly path: string
  readonly method: string
  readonly headers: Readonly<Record<string, string | string[] | undefined>>
}

function headerValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value
}

function digestOf(error: unknown): string | undefined {
  if (typeof error !== "object" || error === null || !("digest" in error)) return undefined
  return typeof error.digest === "string" ? error.digest : undefined
}

export function formatRequestError(
  error: unknown,
  request: ErrorRequest,
  now = new Date(),
): string {
  const time = now.toISOString().replace(/\.\d{3}Z$/, "Z")
  const requestId = headerValue(request.headers["x-request-id"]) ?? "-"
  // 同 api 的請求紀錄: query string 可能帶著敏感內容, 不長期留在 log 裡。
  const path = request.path.split("?")[0]
  // 換行會讓一筆錯誤看起來像好幾行紀錄, 也能被拿來偽造一行假的紀錄。
  const message = String(error).replace(/[\r\n]+/g, " ")
  return `ERROR:   [${time}] [${requestId}] digest=${digestOf(error) ?? "-"} ${request.method} ${path} ${message}`
}
