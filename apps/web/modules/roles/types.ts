// Entity 型別一律從 @/shared/api/entities 取得（那裡由後端 OpenAPI 自動產生）。
// 這個檔案只負責：(1) 給共用型別一個貼近本畫面語意的名字，(2) 放本畫面專屬的型別。
import type { AssignablePermission, Permission, PermissionInfo } from "@/shared/api/entities"

export type { CurrentUser, RoleInfo } from "@/shared/api/entities"

/** 可指派給一般角色的權限 —— 不含超級管理者的萬用字元 `*`。 */
export type PermissionValue = AssignablePermission

/** 角色實際可持有的權限，含超級管理者的 `*`（只有系統角色會有）。 */
export type RolePermissionValue = Permission

/** `GET /permissions/` 回傳的可勾選項目。 */
export type PermissionOption = PermissionInfo

export type RoleFilters = {
  name: string
  isDisabled: string
}
