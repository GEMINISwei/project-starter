// Entity 型別一律從 @/shared/api/entities 取得（那裡由後端 OpenAPI 自動產生）。
export type { CurrentUser, RoleInfo, UserInfo } from "@/shared/api/entities"

export type UserFilters = {
  name: string
  roleId: string
  isDisabled: string
}

// 重設密碼沒有對應的 request body schema（id 走路徑、password 走 body），所以這組欄位
// 手寫在這裡，讓 resetUserPassword 的 FormData 一樣有型別可綁。
export type ResetPasswordFormValues = {
  id: string
  password: string
}
