import { describe, expect, it } from "vitest"
import type { Permission } from "@/shared/api/entities"
import { canAccessRoute, coversPermissions, hasAllPermission } from "@/shared/access/permissions"

// 用與專案無關的權限值: 這裡只驗判斷邏輯。寫成這個專案真的有的權限 (`users:read`) 的話,
// 刪掉那個模組時這支 shared 的測試會跟著壞。
const READ = "things:read" as unknown as Permission
const OTHER = "others:read" as unknown as Permission

describe("hasAllPermission", () => {
  it("只有拿到萬用字元才算超級管理者", () => {
    expect(hasAllPermission(["*"])).toBe(true)
    expect(hasAllPermission([READ, OTHER])).toBe(false)
    expect(hasAllPermission([])).toBe(false)
  })
})

describe("canAccessRoute", () => {
  const readRoute = { requires: [READ] }
  const openRoute = { requires: [] }

  it("requires 為空的路由對所有登入者開放", () => {
    expect(canAccessRoute([], openRoute)).toBe(true)
  })

  it("持有所需權限就能進入", () => {
    expect(canAccessRoute([READ], readRoute)).toBe(true)
  })

  it("沒有所需權限就進不去", () => {
    expect(canAccessRoute([OTHER], readRoute)).toBe(false)
    expect(canAccessRoute([], readRoute)).toBe(false)
  })

  it("超級管理者的萬用字元一律通過", () => {
    expect(canAccessRoute(["*"], readRoute)).toBe(true)
  })

  it("requires 有多個時持有任一個即可", () => {
    const either = { requires: [READ, OTHER] }

    expect(canAccessRoute([OTHER], either)).toBe(true)
  })
})

describe("coversPermissions", () => {
  it("持有的權限涵蓋所有要求的權限才算", () => {
    expect(coversPermissions([READ, OTHER], [READ])).toBe(true)
    expect(coversPermissions([READ], [READ, OTHER])).toBe(false)
  })

  it("萬用字元涵蓋一切，但一般權限涵蓋不了萬用字元", () => {
    expect(coversPermissions(["*"], [READ, "*"])).toBe(true)
    expect(coversPermissions([READ, OTHER], ["*"])).toBe(false)
  })

  it("沒有要求任何權限時一律涵蓋", () => {
    expect(coversPermissions([], [])).toBe(true)
  })
})
