import { describe, expect, it } from "vitest"
import { getApiFieldErrors, getApiResponseErrorMessage } from "@/shared/api/error"
import type { ApiResponse } from "@/shared/api/contract"

describe("getApiResponseErrorMessage", () => {
  it("優先用後端回的 detail", () => {
    const res: ApiResponse = {
      status: "failure",
      code: 400,
      data: { detail: "帳號已存在" },
      message: "POST /users Failure",
    }

    expect(getApiResponseErrorMessage(res, "預設訊息")).toBe("帳號已存在")
  })

  it("detail 是空字串時退到 message", () => {
    const res: ApiResponse = {
      status: "error",
      code: 999,
      data: { detail: "" },
      message: "Api Post Server Error",
    }

    expect(getApiResponseErrorMessage(res, "預設訊息")).toBe("Api Post Server Error")
  })

  it("detail 與 message 都沒有時才用 fallback", () => {
    const res: ApiResponse = {
      status: "failure",
      code: 400,
      data: { detail: "" },
      message: "",
    }

    expect(getApiResponseErrorMessage(res, "預設訊息")).toBe("預設訊息")
  })

  it("成功回應不會被當成錯誤去取 detail", () => {
    // success 的 data 沒有 detail 欄位；這裡驗證窄化有生效、不會回傳 undefined。
    const res: ApiResponse = { status: "success", code: 200, data: {}, message: "ok" }

    expect(getApiResponseErrorMessage(res, "預設訊息")).toBe("ok")
  })
})

describe("getApiFieldErrors", () => {
  it("取出 422 的欄位級錯誤", () => {
    const res: ApiResponse = {
      status: "failure",
      code: 422,
      data: {
        detail: "驗證失敗",
        fieldErrors: { "body → password": "至少 8 個字元" },
      },
      message: "failed",
    }

    expect(getApiFieldErrors(res)).toEqual({ "body → password": "至少 8 個字元" })
  })

  it("失敗但沒有欄位錯誤時回空物件", () => {
    const res: ApiResponse = {
      status: "failure",
      code: 400,
      data: { detail: "帳號已存在" },
      message: "failed",
    }

    expect(getApiFieldErrors(res)).toEqual({})
  })

  it("成功回應回空物件，表單不會殘留上一次的欄位錯誤", () => {
    const res: ApiResponse = { status: "success", code: 200, data: {}, message: "ok" }

    expect(getApiFieldErrors(res)).toEqual({})
  })
})
