import type { ApiResponse } from "@/shared/api/contract"
import type { PaginatedResponse, SimpleListResponse } from "@/shared/api/entities"

// 這些 helper 刻意**不做型別斷言**。型別是從呼叫端的 `apiGet<T>` 流下來的，
// 因此後端改欄位時錯誤會出現在呼叫端的 tsc，而不是等到 runtime 才變成 undefined。

export const getApiListData = <T>(
  res: ApiResponse<PaginatedResponse<T>> | ApiResponse<SimpleListResponse<T>>
): T[] => {
  return res.status === "success" ? res.data.list_data ?? [] : []
}

export const getApiItemData = <T>(res: ApiResponse<T>): T | null => {
  return res.status === "success" ? res.data : null
}

export type ApiListMeta = {
  nextCursor: string | null
  prevCursor: string | null
  hasNext: boolean
  hasPrevious: boolean
  totalCount: number | null
}

const EMPTY_META: ApiListMeta = {
  nextCursor: null,
  prevCursor: null,
  hasNext: false,
  hasPrevious: false,
  totalCount: null,
}

export const getApiListMeta = <T>(res: ApiResponse<PaginatedResponse<T>>): ApiListMeta => {
  if (res.status !== "success") {
    return EMPTY_META
  }

  return {
    nextCursor: res.data.next_cursor ?? null,
    prevCursor: res.data.prev_cursor ?? null,
    hasNext: Boolean(res.data.has_next),
    hasPrevious: Boolean(res.data.has_previous),
    totalCount: res.data.total_count ?? null,
  }
}
