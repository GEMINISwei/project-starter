import { describe, expect, it } from "vitest"
import { canAccessRoute, hasAllPermission } from "@/shared/access/permissions"

describe("hasAllPermission", () => {
  it("只有拿到萬用字元才算超級管理者", () => {
    expect(hasAllPermission(["*"])).toBe(true)
    expect(hasAllPermission(["users:manage", "roles:manage"])).toBe(false)
    expect(hasAllPermission([])).toBe(false)
  })
})

describe("canAccessRoute", () => {
  const usersRoute = { requires: ["users:read"] } as const
  const openRoute = { requires: [] } as const

  it("requires 為空的路由對所有登入者開放", () => {
    expect(canAccessRoute([], openRoute)).toBe(true)
  })

  it("持有所需權限就能進入", () => {
    expect(canAccessRoute(["users:read"], usersRoute)).toBe(true)
  })

  it("沒有所需權限就進不去", () => {
    expect(canAccessRoute(["roles:read"], usersRoute)).toBe(false)
    expect(canAccessRoute([], usersRoute)).toBe(false)
  })

  it("超級管理者的萬用字元一律通過", () => {
    expect(canAccessRoute(["*"], usersRoute)).toBe(true)
  })

  it("requires 有多個時持有任一個即可", () => {
    const either = { requires: ["users:read", "roles:read"] } as const

    expect(canAccessRoute(["roles:read"], either)).toBe(true)
  })

})
