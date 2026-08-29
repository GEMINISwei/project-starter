// `ApiResponse` 是以 status 為 discriminant 的辨識聯集，所以這裡先窄化再取 detail，
// 不需要（也不該）用索引存取去戳一個可能不存在的欄位。

import type { ApiResponse } from "@/shared/api/contract"

const isFailure = <T>(
  res: ApiResponse<T>
): res is Extract<ApiResponse<T>, { status: "failure" | "error" }> => {
  return res.status === "failure" || res.status === "error"
}

export const getApiResponseErrorMessage = <T>(res: ApiResponse<T>, fallback: string) => {
  if (isFailure(res) && res.data.detail) {
    return res.data.detail
  }

  return res.message || fallback
}

/**
 * 取出欄位級驗證錯誤（HTTP 422），key 為後端回報的欄位路徑。
 * 表單可以用它把錯誤標在對應的輸入框上，而不是只顯示一句籠統訊息。
 */
export const getApiFieldErrors = <T>(res: ApiResponse<T>): Record<string, string> => {
  return isFailure(res) ? res.data.fieldErrors ?? {} : {}
}
