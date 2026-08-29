import { describe, expect, it } from "vitest"
import { isRedirectError } from "@/shared/api/redirect"

/**
 * `shared/api/request.server.ts` 的 catch block 用這個判斷來決定「要不要把例外往外丟」。
 *
 * 判斷錯的後果是無聲的：Next.js 的 redirect() 是靠丟出一個帶 `NEXT_REDIRECT` digest 的
 * 例外來運作的。若這裡誤判成一般錯誤，redirect 會被 catch 吞掉、包成一個「Server Error」
 * 回應——使用者該被導去登入頁，卻只看到一則錯誤訊息。
 */
describe("isRedirectError", () => {
  it("認得 Next.js 的 redirect 例外", () => {
    expect(isRedirectError({ digest: "NEXT_REDIRECT;replace;/login;307;" })).toBe(true)
  })

  it("只比對前綴，後面的參數不影響判斷", () => {
    expect(isRedirectError({ digest: "NEXT_REDIRECT" })).toBe(true)
  })

  it("一般 Error 不算 redirect", () => {
    expect(isRedirectError(new Error("network failed"))).toBe(false)
  })

  it("帶 digest 但不是 NEXT_REDIRECT 的例外不算（例如 NEXT_NOT_FOUND）", () => {
    expect(isRedirectError({ digest: "NEXT_NOT_FOUND" })).toBe(false)
  })

  it("null / undefined / 純值都不會讓判斷爆掉", () => {
    expect(isRedirectError(null)).toBe(false)
    expect(isRedirectError(undefined)).toBe(false)
    expect(isRedirectError("NEXT_REDIRECT")).toBe(false)
    expect(isRedirectError(123)).toBe(false)
  })

  it("沒有 digest 欄位的物件不算", () => {
    expect(isRedirectError({ message: "boom" })).toBe(false)
  })
})
