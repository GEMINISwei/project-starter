// 分頁 URL 參數的解析。純函式，和會發 request 的 `fetchPaginatedList` 分開放：後者會拉進帶
// "server-only" 的 request.server.ts，混在一起會讓這段最該被測的解析邏輯反而測不了。

export type PaginationSearchParams = {
  cursor?: string
  direction?: string
  seq?: string
}

export type ParsedPagination = {
  cursor: string | undefined
  direction: "next" | "prev"
  seq: number
}

/**
 * 把 searchParams 轉成可信任的分頁狀態。
 *
 * 這些值直接來自網址，使用者可以任意竄改，所以一律做白名單／範圍檢查：
 * `direction` 只認得 "prev"，`seq` 只接受正整數，其餘都退回安全預設值。
 * `cursor` 對前端是不透明字串，驗證交給後端（壞掉的游標會得到 400）。
 */
export function parsePagination(params?: PaginationSearchParams): ParsedPagination {
  const seq = Number(params?.seq)

  return {
    cursor: params?.cursor,
    direction: params?.direction === "prev" ? "prev" : "next",
    seq: Number.isInteger(seq) && seq > 0 ? seq : 1,
  }
}

/**
 * 解析 URL 中的布林篩選。只有明確的 true/false 會通過，其餘都視為未篩選。
 * 回傳字串是為了能直接傳入既有 API query，而不改變 wire contract。
 */
export function parseBooleanFilter(value?: string): "true" | "false" | "" {
  return value === "true" || value === "false" ? value : ""
}
