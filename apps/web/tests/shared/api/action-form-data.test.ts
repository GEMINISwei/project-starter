import { describe, expect, it } from "vitest"
import {
  createActionFormData,
  getActionFormString,
  getActionFormStrings,
} from "@/shared/api/action-form-data"

describe("Server Action FormData", () => {
  it("保留字串與多值欄位並略過 undefined", () => {
    const data = createActionFormData({
      username: "demo",
      password: "secret",
      role_ids: ["role-a", "role-b"],
      omitted: undefined,
    })

    expect(getActionFormString(data, "username")).toBe("demo")
    expect(getActionFormString(data, "password")).toBe("secret")
    expect(getActionFormStrings(data, "role_ids")).toEqual(["role-a", "role-b"])
    expect(data.has("omitted")).toBe(false)
  })

  it("缺少或非字串欄位會回傳安全預設值", () => {
    const data = createActionFormData({ upload: undefined, other: "x" })
    data.append("upload", new File(["content"], "demo.txt"))

    expect(getActionFormString(data, "upload")).toBe("")
    expect(getActionFormStrings(data, "upload")).toEqual([])
  })

  // 這個 case 沒有執行期斷言，它守的是型別：欄位名是組裝端與讀取端唯一的接縫，
  // 打錯字必須在 tsc 就紅。拿掉 ActionFormData 的 phantom type 會讓這行不再報錯而失敗。
  it("讀取不存在的欄位名是編譯錯誤", () => {
    const data = createActionFormData({ username: "demo" })

    // @ts-expect-error "usernmae" 不在 createActionFormData 收到的欄位裡
    expect(getActionFormString(data, "usernmae")).toBe("")
  })
})
