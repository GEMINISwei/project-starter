import { describe, expect, it } from "vitest"
import { getItemCapabilities } from "@/modules/items/capabilities"

describe("item capabilities", () => {
  it("只解析 items 自己的能力", () => {
    expect(getItemCapabilities(["items:create"])).toEqual({
      canCreateItem: true,
      canUpdateItem: false,
      canDeleteItem: false,
    })
  })

  it("萬用權限取得所有 items 能力", () => {
    expect(Object.values(getItemCapabilities(["*"])).every(Boolean)).toBe(true)
  })
})
