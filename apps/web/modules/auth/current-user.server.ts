import "server-only"
import { cache } from "react"
import { apiGet } from "@/shared/api/request.server"
import { getApiResponseErrorMessage } from "@/shared/api/error"
import { hasAllPermission } from "@/shared/access/permissions"
import { getT } from "@/shared/i18n/locale.server"
import { authMessages } from "./i18n"

// 「目前登入的是誰」屬於登入狀態, 所以住在 auth: 它呼叫的雖然是 users 的端點,
// 放進 users 的話 roles 要引用 users、users 又引用 roles, 兩個模組會互相依賴。
// 也放不進 shared: 它用到 auth 自己的字串, 而 shared 不可引用模組。

// `cache()` 讓同一次 render 內多個 Server Component 呼叫只會真的打一次 /users/me。
export const getCurrentUser = cache(async () => {
  const t = await getT(authMessages)
  // 回應型別由 url 自動推導為 CurrentUser。
  const res = await apiGet({ url: "/users/me" })
  const data = res.status === "success" ? res.data : null
  // permissions 的型別由 OpenAPI 契約保證, 不需要再手動 runtime 過濾一次。
  const isSuperUser = hasAllPermission(data?.permissions ?? [])
  const errorMessage = res.status === "success" ? "" : getApiResponseErrorMessage(res, t("currentUserFailed"))

  return { res, data, isSuperUser, errorMessage }
})
