import { beforeEach, describe, expect, it, vi } from "vitest"

const apiGet = vi.fn()
vi.mock("@/shared/api/request.server", () => ({ apiGet }))

const pagination = await import("@/shared/pagination/fetch.server")

// 與專案無關的路徑並放寬型別 (理由同 tests/shared/api/request.server.test.ts): `url` 的型別是
// 「這個專案有哪些分頁端點」, 寫死成 `/roles/` 的話 shared 一移植就編譯不過。
const fetchPaginatedList = pagination.fetchPaginatedList as unknown as (
  options: Omit<Parameters<typeof pagination.fetchPaginatedList>[0], "url"> & { url: string },
) => ReturnType<typeof pagination.fetchPaginatedList>

describe("fetchPaginatedList", () => {
  beforeEach(() => apiGet.mockReset())

  it("把分頁參數與篩選條件組進 query；沒有游標時不送 cursor", async () => {
    apiGet.mockResolvedValue({
      status: "success",
      data: { list_data: [{ id: "r1" }], has_next: true, has_previous: false, total_count: 3, next_cursor: "c2" },
    })

    const result = await fetchPaginatedList({
      url: "/things/",
      limit: 10,
      direction: "next",
      query: { name: "admin" },
      errorFallback: "載入失敗",
    })

    expect(apiGet.mock.calls[0][0].query).toEqual({ limit: 10, direction: "next", name: "admin" })
    expect(result.items).toEqual([{ id: "r1" }])
    expect(result.meta).toMatchObject({ hasNext: true, nextCursor: "c2", totalCount: 3 })
    expect(result.errorMessage).toBe("")
  })

  it("失敗時給空清單與錯誤訊息，畫面照樣畫得出來", async () => {
    apiGet.mockResolvedValue({ status: "error", data: { detail: "Api Get Server Error" } })

    const result = await fetchPaginatedList({
      url: "/things/",
      limit: 10,
      cursor: "c1",
      direction: "prev",
      errorFallback: "載入失敗",
    })

    expect(apiGet.mock.calls[0][0].query).toMatchObject({ cursor: "c1", direction: "prev" })
    expect(result.items).toEqual([])
    expect(result.errorMessage).not.toBe("")
  })
})
