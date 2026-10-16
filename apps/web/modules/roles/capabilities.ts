import type { PermissionOption, RoleInfo } from "./types"

/**
 * 這個角色能不能編輯 (改名、停用、改權限)。
 *
 * 系統角色 (有 `code`) 整個由模板擁有, 後端一律拒絕修改。這個模組的畫面只有超級管理者
 * 進得來 (`admin/layout.tsx`), 所以不必再看操作者的權限。
 */
export function canManageRole(role: RoleInfo) {
  return role.code === null
}

export type PermissionGroup = {
  category: string
  options: PermissionOption[]
}

/**
 * 依後端給的 `category` 分組, 組與組內的順序都照後端回來的順序 (各 module 的宣告順序)。
 *
 * 標籤與分類都來自後端 (`GET /roles/permission-options`), 前端不另外維護一份 ——
 * 新增 module 時不必回頭改這裡, 後端也在啟動時就保證每個權限都有標籤。
 */
export function groupPermissionOptions(options: readonly PermissionOption[]): PermissionGroup[] {
  const groups = new Map<string, PermissionOption[]>()
  for (const option of options) {
    groups.set(option.category, [...(groups.get(option.category) ?? []), option])
  }
  return [...groups].map(([category, grouped]) => ({ category, options: grouped }))
}
