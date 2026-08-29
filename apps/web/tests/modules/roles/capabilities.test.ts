import { describe, expect, it } from "vitest"
import { getRoleCapabilities } from "@/modules/roles/capabilities"

describe("role capabilities", () => {
  it("只解析 roles 自己的能力", () => {
    expect(getRoleCapabilities(["roles:update"])).toEqual({
      canCreateRole: false,
      canUpdateRole: true,
    })
  })
})
