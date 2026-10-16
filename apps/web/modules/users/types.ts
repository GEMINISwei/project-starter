// Entity 型別一律由後端 OpenAPI 衍生 (`Schema<"…">`), 不手寫形狀。
import type { Schema } from "@/shared/api/contract"

export type UserInfo = Schema<"UserInfo">

export type RoleInfo = Schema<"RoleInfo">

/** `GET /users/me` 的回應: 目前登入者。 */
export type CurrentUser = Schema<"UserMe">

export type UserFilters = {
  name: string
  roleId: string
  isDisabled: string
}

// 重設密碼沒有對應的 request body schema (id 走路徑、password 走 body), 所以這組欄位
// 手寫在這裡, 讓 resetUserPassword 的 FormData 一樣有型別可綁。
export type ResetPasswordFormValues = {
  id: string
  password: string
}
