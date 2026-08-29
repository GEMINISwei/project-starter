import { describe, expect, it } from "vitest"
import { getApiItemData, getApiListData, getApiListMeta } from "@/shared/api/response"
import type { ApiResponse } from "@/shared/api/contract"
import type { PaginatedResponse, SimpleListResponse } from "@/shared/api/entities"

type Item = { id: string }

const success = <T>(data: T): ApiResponse<T> => ({
  status: "success",
  code: 200,
  data,
  message: "ok",
})

const failure = <T>(detail = "壞了"): ApiResponse<T> => ({
  status: "failure",
  code: 400,
  data: { detail },
  message: "failed",
})

describe("getApiListData", () => {
  it("成功時取出 list_data", () => {
    const res = success<PaginatedResponse<Item>>({
      list_data: [{ id: "a" }, { id: "b" }],
      has_next: false,
      has_previous: false,
      total_count: 2,
    })

    expect(getApiListData(res)).toEqual([{ id: "a" }, { id: "b" }])
  })

  it("非分頁的 SimpleListResponse 也走同一條路", () => {
    const res = success<SimpleListResponse<Item>>({ list_data: [{ id: "a" }], count: 1 })

    expect(getApiListData(res)).toEqual([{ id: "a" }])
  })

  it("失敗時回空陣列，呼叫端不必再判斷 status", () => {
    // 這是這層存在的理由：列表頁可以無條件 map 結果，錯誤訊息另外從 errorMessage 取。
    expect(getApiListData(failure<PaginatedResponse<Item>>())).toEqual([])
  })

  it("list_data 缺漏時回空陣列而不是 undefined", () => {
    const res = success({ has_next: false, has_previous: false } as PaginatedResponse<Item>)

    expect(getApiListData(res)).toEqual([])
  })
})

describe("getApiItemData", () => {
  it("成功時回傳資料本身", () => {
    expect(getApiItemData(success<Item>({ id: "a" }))).toEqual({ id: "a" })
  })

  it("失敗時回 null（而不是丟例外或回空物件）", () => {
    expect(getApiItemData(failure<Item>())).toBeNull()
  })
})

describe("getApiListMeta", () => {
  it("成功時把後端的 snake_case 欄位轉成前端的 camelCase 形狀", () => {
    const res = success<PaginatedResponse<Item>>({
      list_data: [],
      next_cursor: "next-token",
      prev_cursor: "prev-token",
      has_next: true,
      has_previous: true,
      total_count: 42,
    })

    expect(getApiListMeta(res)).toEqual({
      nextCursor: "next-token",
      prevCursor: "prev-token",
      hasNext: true,
      hasPrevious: true,
      totalCount: 42,
    })
  })

  it("null / 缺漏的欄位一律正規化成 null 或 false", () => {
    // 後端對「沒有下一頁」回的是 null cursor；前端不該讓 undefined 與 null 兩種空值並存。
    //
    // `total_count: null` 在型別上已經不合法（契約規定它必填），這裡刻意用 cast 造出
    // 一個違反契約的回應 —— 因為 `ApiResponse` 的 data 是從網路來的，型別只是契約，
    // 不是執行期保證。`getApiListMeta` 的正規化就是為了這種情況存在，測試必須能觸及它。
    const res = success<PaginatedResponse<Item>>({
      list_data: [],
      next_cursor: null,
      prev_cursor: null,
      has_next: false,
      has_previous: false,
      total_count: null as unknown as number,
    })

    expect(getApiListMeta(res)).toEqual({
      nextCursor: null,
      prevCursor: null,
      hasNext: false,
      hasPrevious: false,
      totalCount: null,
    })
  })

  it("失敗時回一組安全的空 meta，分頁 UI 不會顯示假的翻頁狀態", () => {
    expect(getApiListMeta(failure<PaginatedResponse<Item>>())).toEqual({
      nextCursor: null,
      prevCursor: null,
      hasNext: false,
      hasPrevious: false,
      totalCount: null,
    })
  })

  it("total_count 為 0 時保留 0，不會被當成空值換成 null", () => {
    const res = success<PaginatedResponse<Item>>({
      list_data: [],
      has_next: false,
      has_previous: false,
      total_count: 0,
    })

    expect(getApiListMeta(res).totalCount).toBe(0)
  })
})
