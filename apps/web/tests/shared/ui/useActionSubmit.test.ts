import { act, renderHook, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { useActionSubmit } from "@/shared/ui/hooks/useActionSubmit"
import { parseErrorDetail } from "@/shared/api/payload"
import type { ApiResponse } from "@/shared/api/contract"

const response = (res: ApiResponse) => () => Promise.resolve(res)

describe("useActionSubmit", () => {
  it("success 會走 onSuccess，不會呼叫 onError", async () => {
    const onSuccess = vi.fn()
    const onError = vi.fn()
    const { result } = renderHook(() => useActionSubmit())

    act(() => {
      result.current.submit(response({ status: "success", code: 200, data: {}, message: "ok" }), {
        onSuccess,
        onError,
      })
    })

    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1))
    expect(onError).not.toHaveBeenCalled()
  })

  it("info（204 無變更）也算成功", async () => {
    // 後端對「送出了但沒有任何欄位真的改變」回 204，由 api.ts 包成 status: "info"。
    // 這不是錯誤，對話框應該正常關閉，而不是跳一則紅色訊息。
    const onSuccess = vi.fn()
    const onError = vi.fn()
    const { result } = renderHook(() => useActionSubmit())

    act(() => {
      result.current.submit(
        response({ status: "info", code: 204, data: {}, message: "PATCH No Change" }),
        { onSuccess, onError }
      )
    })

    await waitFor(() => expect(onSuccess).toHaveBeenCalledTimes(1))
    expect(onError).not.toHaveBeenCalled()
  })

  it("failure 會走 onError 並帶上後端的 detail", async () => {
    const onSuccess = vi.fn()
    const onError = vi.fn()
    const { result } = renderHook(() => useActionSubmit())

    act(() => {
      result.current.submit(
        response({
          status: "failure",
          code: 400,
          data: { detail: "帳號已存在" },
          message: "failed",
        }),
        { onSuccess, onError }
      )
    })

    await waitFor(() => expect(onError).toHaveBeenCalledWith("帳號已存在"))
    expect(onSuccess).not.toHaveBeenCalled()
  })

  // 這一條刻意從 FastAPI 原始形狀的 detail 陣列出發，而不是手寫 fieldErrors：
  // 欄位名怎麼從 loc 變出來是 payload.ts 決定的，兩邊各自手寫字面值的話，
  // 那條約定飄開時兩邊的測試都還是綠的。
  it("422 會把欄位級錯誤交給呼叫端，key 就是欄位名", async () => {
    const onError = vi.fn()
    const parsed = parseErrorDetail([{ loc: ["body", "password"], msg: "至少 8 個字元" }])
    const { result } = renderHook(() => useActionSubmit())

    act(() => {
      result.current.submit(
        response({
          status: "failure",
          code: 422,
          data: { detail: parsed.message, fieldErrors: parsed.fieldErrors },
          message: "failed",
        }),
        { onSuccess: vi.fn(), onError }
      )
    })

    await waitFor(() => expect(result.current.fieldError("password")).toBe("至少 8 個字元"))
    // toast 不該漏出 loc 的位置前綴。
    expect(onError).toHaveBeenCalledWith("password: 至少 8 個字元")
  })

  it("對話框關閉時可以清除欄位級錯誤", async () => {
    const { result } = renderHook(() => useActionSubmit())

    act(() => {
      result.current.submit(
        response({
          status: "failure",
          code: 422,
          data: { detail: "name: 欄位無效", fieldErrors: { name: "欄位無效" } },
          message: "failed",
        }),
        { onSuccess: vi.fn(), onError: vi.fn() }
      )
    })
    await waitFor(() => expect(result.current.fieldError("name")).toBe("欄位無效"))

    act(() => result.current.clearFieldErrors())

    expect(result.current.fieldError("name")).toBeUndefined()
  })

  it("沒有 detail 與 message 時使用呼叫端給的 errorFallback", async () => {
    const onError = vi.fn()
    const { result } = renderHook(() => useActionSubmit())

    act(() => {
      result.current.submit(
        response({ status: "error", code: 999, data: { detail: "" }, message: "" }),
        { onSuccess: vi.fn(), onError, errorFallback: "建立角色失敗" }
      )
    })

    await waitFor(() => expect(onError).toHaveBeenCalledWith("建立角色失敗"))
  })

  it("沒有指定 errorFallback 時退回預設的「操作失敗」", async () => {
    const onError = vi.fn()
    const { result } = renderHook(() => useActionSubmit())

    act(() => {
      result.current.submit(
        response({ status: "error", code: 999, data: { detail: "" }, message: "" }),
        { onSuccess: vi.fn(), onError }
      )
    })

    await waitFor(() => expect(onError).toHaveBeenCalledWith("操作失敗"))
  })

  it("送出完成後 isPending 會回到 false", async () => {
    const { result } = renderHook(() => useActionSubmit())

    expect(result.current.isPending).toBe(false)

    act(() => {
      result.current.submit(response({ status: "success", code: 200, data: {}, message: "ok" }), {
        onSuccess: vi.fn(),
        onError: vi.fn(),
      })
    })

    await waitFor(() => expect(result.current.isPending).toBe(false))
  })
})
