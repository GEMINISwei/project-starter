// @vitest-environment node

import { describe, expect, it } from "vitest"
import { formatRequestError } from "@/shared/runtime/request-error"

/**
 * Next 伺服器端的錯誤要能用 request id 對上 nginx 與 api 的紀錄, 用 digest 對上使用者
 * 截圖裡的錯誤代碼 (docs/operations.md)。
 */

const NOW = new Date("2026-11-10T06:03:22.123Z")

function request(path: string, headers: Record<string, string> = {}) {
  return { path, method: "POST", headers }
}

describe("formatRequestError", () => {
  it("伺服器端錯誤印出 request id、digest、方法與路徑", () => {
    const error = Object.assign(new Error("fetch failed"), { digest: "3847261950" })

    const line = formatRequestError(error, request("/users/new", { "x-request-id": "a1b2c3d4" }), NOW)

    expect(line).toBe(
      "ERROR:   [2026-11-10T06:03:22Z] [a1b2c3d4] digest=3847261950 POST /users/new Error: fetch failed",
    )
  })

  it("沒有 request id 與 digest 時印 -", () => {
    const line = formatRequestError(new Error("boom"), request("/"), NOW)

    expect(line).toContain("[-] digest=- POST / ")
  })

  it("路徑不含 query string，敏感內容不長期留在 log 裡", () => {
    const line = formatRequestError(new Error("boom"), request("/search?token=secret"), NOW)

    expect(line).toContain("POST /search ")
    expect(line).not.toContain("secret")
  })
})
