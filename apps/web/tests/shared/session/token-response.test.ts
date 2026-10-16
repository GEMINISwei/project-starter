import { describe, expect, it } from "vitest"
import type { ApiResponse } from "@/shared/api/contract"
import { withoutAccessToken } from "@/shared/session/token-response"

/**
 * Server Action 的回傳值會被序列化送進瀏覽器。token 已經寫進 httpOnly cookie,
 * 再原樣回傳的話, 任何 XSS 都能從回傳值拿到完整的 JWT —— httpOnly 等於沒設。
 *
 * 「每個寫 cookie 的 action 都有呼叫它」是專案層級的規則, 在 `tests/token-cookie-writers.test.ts`。
 */
describe("withoutAccessToken", () => {
  it("成功回應拿掉 access_token，其餘欄位保留", () => {
    const res: ApiResponse<{ access_token: string; token_type: string }> = {
      status: "success",
      code: 200,
      data: { access_token: "jwt", token_type: "bearer" },
      message: "",
    }

    const stripped = withoutAccessToken(res)

    expect(JSON.stringify(stripped)).not.toContain("jwt")
    expect(stripped).toEqual({ status: "success", code: 200, data: { token_type: "bearer" }, message: "" })
  })

  it("失敗回應原樣傳回", () => {
    const res: ApiResponse<{ access_token: string }> = {
      status: "failure",
      code: 401,
      data: { detail: "nope" },
      message: "nope",
    }

    expect(withoutAccessToken(res)).toBe(res)
  })
})
