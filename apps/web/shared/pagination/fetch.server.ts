import { apiGet } from "@/shared/api/request.server"
import { getApiResponseErrorMessage } from "@/shared/api/error"
import { getApiListData, getApiListMeta, type ApiListMeta } from "@/shared/api/response"
import type { ApiPathsFor, ApiSuccessData, DataObject } from "@/shared/api/contract"

// URL 參數的解析在 shared/pagination/query.ts（純函式、可單元測試）。只轉出 `parsePagination`
// 讓 page.server 一個 import 就拿得到；型別不轉出，呼叫端都是靠推導拿到的（knip 會擋）。
export { parsePagination } from "@/shared/pagination/query"

/**
 * 只有「回應是游標分頁形狀」的 GET 端點能傳給 `fetchPaginatedList`。
 *
 * 把約束寫在型別上，而不是靠註解提醒：拿 `/permissions/`（`SimpleListResponse`，
 * 沒有游標欄位）去呼叫分頁函式，會直接是編譯錯誤。
 */
type PaginatedGetPath = {
  [P in ApiPathsFor<"get">]: ApiSuccessData<P, "get"> extends { list_data: unknown[]; has_next: boolean }
    ? P
    : never
}[ApiPathsFor<"get">]

/** 從端點的回應形狀反推列表元素的型別（`{ list_data: T[] }` → `T`）。 */
type ListItem<P extends ApiPathsFor<"get">> =
  ApiSuccessData<P, "get"> extends { list_data: (infer I)[] } ? I : never

/**
 * 抓一頁游標分頁的資料。元素型別由 `url` 推導，端點與回應資料在編譯期保持一致；只接受**回應
 * 是分頁形狀**的端點，不是的話 `items` 會是 `never[]`，用它做任何事都是型別錯誤。
 */
export async function fetchPaginatedList<P extends PaginatedGetPath>(options: {
  url: P
  limit: number
  cursor?: string
  direction: "next" | "prev"
  query?: DataObject
  errorFallback: string
}): Promise<{ items: ListItem<P>[]; meta: ApiListMeta; errorMessage: string }> {
  const res = await apiGet({
    url: options.url,
    query: {
      limit: options.limit,
      direction: options.direction,
      ...(options.cursor ? { cursor: options.cursor } : {}),
      ...options.query,
    },
    // 這個函式對「哪一個」端點是泛型的，TypeScript 無法把上面動態組出的 query 窄化成某一個
    // 端點的 query 型別。斷言只發生在這一個點，`url` 與元素型別仍受 `PaginatedGetPath` 約束。
  } as unknown as Parameters<typeof apiGet<P>>[0])

  return {
    items: getApiListData<ListItem<P>>(res as never),
    meta: getApiListMeta(res as never),
    errorMessage: res.status === "success" ? "" : getApiResponseErrorMessage(res, options.errorFallback),
  }
}
