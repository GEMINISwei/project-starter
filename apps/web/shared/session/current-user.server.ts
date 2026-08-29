import { cache } from "react"
import { apiGet } from "@/shared/api/request.server"
import { getApiResponseErrorMessage } from "@/shared/api/error"
import { hasAllPermission } from "@/shared/access/permissions"
import { getT } from "@/shared/i18n/locale.server"
import { sharedMessages } from "@/shared/i18n/messages"

// `cache()` 讓同一次 render 內多個 Server Component 呼叫只會真的打一次 /users/me。
export const getCurrentUser = cache(async () => {
  const t = await getT(sharedMessages)
  // 回應型別由 url 自動推導為 CurrentUser。
  const res = await apiGet({ url: "/users/me" })
  const data = res.status === "success" ? res.data : null
  // permissions 的型別由 OpenAPI 契約保證，不需要再手動 runtime 過濾一次。
  const isSuperUser = hasAllPermission(data?.permissions ?? [])
  const errorMessage = res.status === "success" ? "" : getApiResponseErrorMessage(res, t("currentUserFailed"))

  return { res, data, isSuperUser, errorMessage }
})
