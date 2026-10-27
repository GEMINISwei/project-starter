/**
 * 前端呼叫後端的唯一出口 (`shared/api/request.server.ts`) 的執行期行為。
 *
 * 型別面 (端點、參數、body 寫錯是編譯錯誤) 由 `tests/modules/roles/api-contract.test-d.ts` 守;
 * 這裡守的是型別管不到的那一半: token 失效時一定導回登入頁、錯誤回應被正確攤平、寫入成功才
 * 更新快取、網路錯誤不會變成未處理的例外。這些壞掉時畫面通常還「看起來正常」。
 *
 * Next 的請求上下文 (cookies/headers/redirect/revalidate) 與 `fetch` 都換成假的,
 * `server-only` 由 vitest.config.ts 換成空模組。
 */

import { beforeEach, describe, expect, it, vi } from "vitest"
import type { ApiResponse } from "@/shared/api/contract"

const cookieJar = new Map<string, string>()
const requestHeaders = new Map<string, string>()
const redirect = vi.fn((url: string) => {
  // 與 Next 的 redirect 一樣丟出帶 NEXT_REDIRECT digest 的錯誤, request.server 要讓它往外跑。
  throw Object.assign(new Error("redirect"), { digest: `NEXT_REDIRECT;replace;${url}` })
})
const revalidatePath = vi.fn()
const clearAccessTokenCookie = vi.fn(async () => cookieJar.delete("access_token"))
const fetchMock = vi.fn()

function readCookie(key: string) {
  return cookieJar.has(key) ? { value: cookieJar.get(key) } : undefined
}

vi.mock("next/headers", () => ({
  cookies: async () => ({ get: readCookie }),
  headers: async () => ({ get: (key: string) => requestHeaders.get(key) ?? null }),
}))
vi.mock("next/navigation", () => ({ redirect }))
vi.mock("next/cache", () => ({ revalidatePath, revalidateTag: vi.fn() }))
vi.mock("@/shared/i18n/locale.server", () => ({ getLocale: async () => "en" }))
vi.mock("@/shared/session/access-token.server", () => ({ clearAccessTokenCookie }))
vi.stubGlobal("fetch", fetchMock)

const api = await import("@/shared/api/request.server")

// 這支測的是執行期行為, 與專案有哪些端點無關。用與專案無關的路徑並放寬型別 —— 寫成這個專案
// 真的有的端點 (`/roles/{id}`) 的話, 刪掉 roles 時這支 shared 的測試會跟著壞。
type LooseRequest = {
  url: string
  params?: Record<string, string>
  auth?: "none" | "required"
  contentType?: "json" | "form-data"
  data?: Record<string, unknown>
  refresh?: { path?: string }
}
type LooseCall = (request: LooseRequest) => Promise<ApiResponse<Record<string, unknown>>>
const apiGet = api.apiGet as unknown as LooseCall
const apiPost = api.apiPost as unknown as LooseCall
const apiPatch = api.apiPatch as unknown as LooseCall

function respond(status: number, body?: unknown) {
  fetchMock.mockResolvedValueOnce(
    new Response(body === undefined ? null : JSON.stringify(body), { status }),
  )
}

function sentRequest() {
  const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
  return { url, init, headers: init.headers as Record<string, string> }
}

beforeEach(() => {
  vi.clearAllMocks()
  cookieJar.clear()
  requestHeaders.clear()
  cookieJar.set("access_token", "jwt")
})

describe("組出請求", () => {
  it("路徑參數會編碼、陣列 query 展開成重複的 key，並帶上 token 與語系", async () => {
    respond(200, { list_data: [], count: 0 })
    requestHeaders.set("x-request-id", "req-1")

    await apiGet({ url: "/things/{id}", params: { id: "a/b" } })

    const { url, headers, init } = sentRequest()
    expect(url).toBe("http://api:8000/api/things/a%2Fb")
    expect(headers["Cookie"]).toBe("access_token=jwt")
    expect(headers["Accept-Language"]).toBe("en")
    expect(headers["X-Request-ID"]).toBe("req-1")
    // GET 預設不快取: 資料一律是這次請求當下的狀態。
    expect((init as { next?: unknown }).next).toEqual({ revalidate: 0 })
  })

  it("form-data 的 body 以 URL 編碼送出，JSON 的以字串送出", async () => {
    respond(200, { access_token: "new", token_type: "bearer" })
    await apiPost({
      url: "/session",
      auth: "none",
      contentType: "form-data",
      data: { username: "u", password: "p" },
    })
    expect(String(sentRequest().init.body)).toBe("username=u&password=p")

    fetchMock.mockClear()
    respond(200, { id: "r1" })
    await apiPost({ url: "/things/", data: { name: "x", permissions: [] } })
    expect(sentRequest().init.body).toBe(JSON.stringify({ name: "x", permissions: [] }))
  })

  it("缺少路徑參數時直接丟錯，不送出一個帶著 {id} 的網址", async () => {
    await expect(apiGet({ url: "/things/{id}", params: {} })).rejects.toThrow(
      /路徑參數缺少 "id"/,
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe("登入狀態", () => {
  it("需要登入卻沒有 token：不送出請求，直接導回登入頁", async () => {
    cookieJar.clear()

    await expect(apiGet({ url: "/me" })).rejects.toMatchObject({
      digest: expect.stringContaining("NEXT_REDIRECT"),
    })
    expect(fetchMock).not.toHaveBeenCalled()
    expect(redirect).toHaveBeenCalledWith("/login?reason=session-expired")
  })

  it("auth: none 的端點沒有 token 也照常送出，而且不帶 Cookie", async () => {
    cookieJar.clear()
    respond(200, { available: true })

    const res = await apiGet({ url: "/status", auth: "none" })

    expect(res.status).toBe("success")
    expect(sentRequest().headers["Cookie"]).toBeUndefined()
  })

  it("後端回 401：清掉 cookie 並導回登入頁（token 過期或被撤銷）", async () => {
    respond(401, { detail: "expired" })

    await expect(apiGet({ url: "/me" })).rejects.toMatchObject({
      digest: expect.stringContaining("NEXT_REDIRECT"),
    })
    expect(clearAccessTokenCookie).toHaveBeenCalled()
    expect(redirect).toHaveBeenCalledWith("/login?reason=session-expired")
  })

  it("清不掉 cookie（Server Component 算繪中）也照樣導回登入頁", async () => {
    clearAccessTokenCookie.mockRejectedValueOnce(new Error("cookies are read-only here"))
    respond(401, { detail: "expired" })

    await expect(apiGet({ url: "/me" })).rejects.toMatchObject({
      digest: expect.stringContaining("NEXT_REDIRECT"),
    })
    expect(redirect).toHaveBeenCalled()
  })
})

describe("判讀回應", () => {
  it("錯誤回應攤平成 detail，422 另外帶上欄位錯誤", async () => {
    respond(422, {
      detail: [{ loc: ["body", "name"], msg: "Field required", type: "missing" }],
    })

    const res = await apiPost({ url: "/things/", data: { name: "", permissions: [] } })

    expect(res.status).toBe("failure")
    expect(res.code).toBe(422)
    if (res.status !== "failure") throw new Error("unreachable")
    expect(res.data.fieldErrors).toBeDefined()
  })

  it("寫入成功才更新快取，失敗不更新", async () => {
    respond(200, { id: "r1" })
    await apiPatch({
      url: "/things/{id}",
      params: { id: "r1" },
      data: { name: "x", permissions: [], is_disabled: false },
      refresh: { path: "/things" },
    })
    expect(revalidatePath).toHaveBeenCalledWith("/things")

    revalidatePath.mockClear()
    respond(403, { detail: "forbidden" })
    await apiPatch({
      url: "/things/{id}",
      params: { id: "r1" },
      data: { name: "x", permissions: [], is_disabled: false },
      refresh: { path: "/things" },
    })
    expect(revalidatePath).not.toHaveBeenCalled()
  })

  it("寫入回 204（沒有變更）時回傳 info，而不是去解析空的 body", async () => {
    respond(204)

    const res = await apiPatch({
      url: "/things/{id}",
      params: { id: "r1" },
      data: { name: "x", permissions: [], is_disabled: false },
    })

    expect(res.status).toBe("info")
    expect(res.code).toBe(204)
  })

  it("連不上後端時回傳 error，不讓例外打斷整個頁面", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("fetch failed"))

    const res = await apiGet({ url: "/me" })

    expect(res.status).toBe("error")
    expect(res.data).toEqual({ detail: "Api Get Server Error" })
  })
})
