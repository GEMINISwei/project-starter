import { describe, expect, it } from "vitest"
import { getBodyData, parseErrorDetail } from "@/shared/api/payload"

describe("getBodyData", () => {
  it("保留空字串，讓使用者能把欄位清空", () => {
    expect(getBodyData({ nickname: "" })).toEqual({ nickname: "" })
  })

  it("濾掉 undefined —— 那才是「不要送這個欄位」的表達方式", () => {
    expect(getBodyData({ name: "a", role_id: undefined })).toEqual({ name: "a" })
  })

  it("保留 false、0、null 等有意義的值", () => {
    expect(getBodyData({ is_disabled: false, count: 0, disabled_at: null })).toEqual({
      is_disabled: false,
      count: 0,
      disabled_at: null,
    })
  })

  it("空物件進、空物件出", () => {
    expect(getBodyData({})).toEqual({})
  })
})

describe("parseErrorDetail", () => {
  it("字串型別的 detail 直接當訊息用", () => {
    expect(parseErrorDetail("帳號已存在")).toEqual({ message: "帳號已存在" })
  })

  it("FastAPI 的 422 陣列會攤平成欄位級錯誤，而不是被丟掉", () => {
    const result = parseErrorDetail([
      { loc: ["body", "password"], msg: "至少 8 個字元" },
      { loc: ["body", "username"], msg: "不可為空" },
    ])

    expect(result.fieldErrors).toEqual({
      password: "至少 8 個字元",
      username: "不可為空",
    })
    expect(result.message).toContain("至少 8 個字元")
    expect(result.message).toContain("不可為空")
  })

  // key 與 message 都不該帶 body/query/path 前綴：前者會逼 useActionSubmit 反推，
  // 後者會讓使用者在 toast 上看到 `body → password: …`。
  it("欄位名不帶 loc 的位置前綴，query 與 path 的錯誤也一樣", () => {
    const result = parseErrorDetail([
      { loc: ["query", "page"], msg: "必須大於 0" },
      { loc: ["path", "id"], msg: "格式錯誤" },
    ])

    expect(result.fieldErrors).toEqual({ page: "必須大於 0", id: "格式錯誤" })
    expect(result.message).not.toContain("query")
    expect(result.message).not.toContain("path")
  })

  it("陣列中格式不符的項目會被略過，不會讓整個解析爆掉", () => {
    const result = parseErrorDetail([null, "字串", { loc: ["body", "x"], msg: "壞了" }])

    expect(result.fieldErrors).toEqual({ x: "壞了" })
  })

  it("無法解析時退回通用訊息", () => {
    expect(parseErrorDetail(undefined).message).toBe("Server Unknown Error")
    expect(parseErrorDetail([]).message).toBe("Server Unknown Error")
    expect(parseErrorDetail({}).message).toBe("Server Unknown Error")
  })

  it("沒有欄位級錯誤時不會硬塞一個空的 fieldErrors", () => {
    expect(parseErrorDetail("一般錯誤").fieldErrors).toBeUndefined()
  })
})
