import { describe, expect, it } from "vitest"
import {
  formatRoleNames, getUserCapabilities, isSuperAdminUser,
} from "@/modules/users/capabilities"
import type { RoleInfo } from "@/modules/users/types"

describe("user capabilities", () => {
  it("區分 update:own 與 update:any", () => {
    const own = getUserCapabilities(["users:update:own"])
    expect(own.canUpdateOwnUser).toBe(true)
    expect(own.canUpdateAnyUser).toBe(false)

    const any = getUserCapabilities(["users:update:any"])
    expect(any.canUpdateAnyUser).toBe(true)
    expect(any.canUpdateOwnUser).toBe(false)
  })

  it("沒有權限時所有能力皆為 false", () => {
    expect(Object.values(getUserCapabilities([])).some(Boolean)).toBe(false)
  })
})

const ROLES: RoleInfo[] = [
  { id: "r-admin", name: "管理員", code: null, permissions: ["*"], is_disabled: false },
  { id: "r-staff", name: "員工", code: null, permissions: ["users:read"], is_disabled: false },
  { id: "r-old", name: "舊職務", code: null, permissions: ["users:read"], is_disabled: true },
]

function user(roleIds: string[]) {
  return {
    id: "u-1", username: "u", nickname: "U",
    role_ids: roleIds, permissions: [], is_disabled: false,
  }
}

describe("isSuperAdminUser", () => {
  it("身上掛著擁有全權限的角色就是超級管理者", () => {
    expect(isSuperAdminUser(user(["r-admin"]), ROLES)).toBe(true)
    expect(isSuperAdminUser(user(["r-staff"]), ROLES)).toBe(false)
  })

  it("角色 id 找不到對應角色時不算，也不會爆掉", () => {
    expect(isSuperAdminUser(user(["r-deleted"]), ROLES)).toBe(false)
  })
})

describe("formatRoleNames", () => {
  const t = ((key: string, vars?: Record<string, unknown>) => {
    if (key === "roleDisabledSuffix") return `${vars?.name}（已停用）`
    if (key === "roleSeparator") return "、"
    return "未指派"
  }) as never
  const roleT = (() => "") as never

  it("多個角色以分隔字串串起來", () => {
    expect(formatRoleNames(user(["r-admin", "r-staff"]), ROLES, t, roleT)).toBe("管理員、員工")
  })

  it("已停用的角色帶後綴", () => {
    expect(formatRoleNames(user(["r-old"]), ROLES, t, roleT)).toBe("舊職務（已停用）")
  })

  it("一個角色都沒有時回傳未指派", () => {
    expect(formatRoleNames(user([]), ROLES, t, roleT)).toBe("未指派")
  })

  it("找不到的角色 id 直接略過，不會變成空字串混進去", () => {
    expect(formatRoleNames(user(["r-deleted", "r-staff"]), ROLES, t, roleT)).toBe("員工")
  })
})
