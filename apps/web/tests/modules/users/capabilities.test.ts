import { describe, expect, it } from "vitest"
import {
  canResetPassword, formatRoleNames, getEditableUserFields, isAssignableRole, isSuperAdminUser,
  roleIdsForUpdate,
} from "@/modules/users/capabilities"
import type { RoleInfo } from "@/modules/users/types"

const ROLES: RoleInfo[] = [
  { id: "r-admin", name: "管理員", code: null, permissions: ["*"], is_disabled: false },
  { id: "r-staff", name: "員工", code: null, permissions: [], is_disabled: false },
  { id: "r-old", name: "舊職務", code: null, permissions: [], is_disabled: true },
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

describe("getEditableUserFields", () => {
  it("編輯別人時可以改角色與狀態", () => {
    expect(getEditableUserFields(user(["r-staff"]), "u-other", ROLES, true)).toEqual({
      canAssignRole: true,
      canToggleStatus: true,
    })
  })

  it("編輯自己時不能改角色、也不能停用自己", () => {
    expect(getEditableUserFields(user([]), "u-1", ROLES, true)).toEqual({
      canAssignRole: false,
      canToggleStatus: false,
    })
  })

  it("超級管理者帳號不能被停用", () => {
    expect(getEditableUserFields(user(["r-admin"]), "u-other", ROLES, true).canToggleStatus)
      .toBe(false)
  })

  // 超管的角色是 `*`, 不在可指派清單裡; 讓它出現在表單上, 送出時只會被後端擋下, 連暱稱都改不了。
  it("超級管理者帳號的角色不能更改", () => {
    expect(getEditableUserFields(user(["r-admin"]), "u-other", ROLES, true).canAssignRole)
      .toBe(false)
  })

  it("沒有可指派的角色時不顯示角色欄位", () => {
    expect(getEditableUserFields(user([]), "u-other", ROLES, false).canAssignRole).toBe(false)
  })
})

describe("roleIdsForUpdate", () => {
  it("可指派角色且選了未指派時送出空陣列", () => {
    expect(roleIdsForUpdate(true, "")).toEqual([])
  })

  it("可指派角色且選了角色時送出該角色", () => {
    expect(roleIdsForUpdate(true, "r-staff")).toEqual(["r-staff"])
  })

  // 送了就會撞上後端的保護規則 (不能改自己、不能改超管的角色)。
  it("不能指派角色時不送 role_ids", () => {
    expect(roleIdsForUpdate(false, "r-staff")).toBeUndefined()
    expect(roleIdsForUpdate(false, "")).toBeUndefined()
  })
})

describe("canResetPassword", () => {
  it("一般帳號可以重設密碼", () => {
    expect(canResetPassword(user(["r-staff"]), ROLES)).toBe(true)
    expect(canResetPassword(user([]), ROLES)).toBe(true)
  })

  // 包含自己: 能進後台的只有超管, 自己一定也是超管。改自己的密碼走設定頁。
  it("超級管理者帳號不能在後台重設密碼", () => {
    expect(canResetPassword(user(["r-admin"]), ROLES)).toBe(false)
  })
})

describe("isAssignableRole", () => {
  it("只列出啟用中、非超管的角色", () => {
    expect(isAssignableRole(ROLES[1])).toBe(true)
    expect(isAssignableRole(ROLES[0])).toBe(false)
    expect(isAssignableRole(ROLES[2])).toBe(false)
  })
})
