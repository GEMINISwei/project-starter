import { beforeEach, describe, expect, it, vi } from "vitest"

// request.server.ts 帶 "server-only"，在測試環境載入不了，所以整個 mock 掉。
const apiGet = vi.fn()
vi.mock("@/shared/api/request.server", () => ({ apiGet: apiGet }))

const { getBootstrapState } = await import("@/modules/auth/bootstrap.server")

describe("getBootstrapState", () => {
  beforeEach(() => apiGet.mockReset())

  it("尚未初始化時回傳 available", async () => {
    apiGet.mockResolvedValue({ status: "success", data: { available: true } })

    await expect(getBootstrapState()).resolves.toBe("available")
  })

  it("已初始化時回傳 completed", async () => {
    apiGet.mockResolvedValue({ status: "success", data: { available: false } })

    await expect(getBootstrapState()).resolves.toBe("completed")
  })

  // 這一條是三態存在的理由：查不到**不等於**已完成，也不等於未完成。
  // 壓成 boolean 的話，後端抖一下就會有一頁做出相反的錯誤決定。
  it.each(["failure", "error"] as const)("查詢 %s 時回傳 unknown", async (status) => {
    apiGet.mockResolvedValue({ status, data: { detail: "boom" } })

    await expect(getBootstrapState()).resolves.toBe("unknown")
  })
})
