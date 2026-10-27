import type { Permission } from "@/shared/api/entities"

// 走 `has()` 而不是直接 `permissions.includes("...")`: 參數標成 Permission 之後,
// 權限字串打錯或後端刪掉某個權限時, 這裡會**編譯失敗**而不是靜默回傳 false。
function includesPermission(permissions: readonly string[], permission: Permission) {
  return permissions.includes(permission)
}

export function hasAllPermission(permissions: readonly string[]) {
  return includesPermission(permissions, "*")
}

function hasPermission(permissions: readonly string[], permission: Permission) {
  return hasAllPermission(permissions) || includesPermission(permissions, permission)
}

function hasAnyPermission(permissions: readonly string[], required: readonly Permission[]) {
  return required.some((permission) => hasPermission(permissions, permission))
}

/**
 * 判斷使用者能不能進入某條路由。
 *
 * 導覽列 (AppShell) 與存取控制 (admin/layout.tsx) 都呼叫這一個函式,
 * 所以不可能出現「側欄看得到但點進去被踢出來」這種不一致。
 *
 * 這只是 UX 層的把關 —— 真正的授權在後端 (`shared/auth/dependency.py` 的
 * `check_user_permission`), 直接打 API 一樣會被擋。
 */
export function canAccessRoute(
  permissions: readonly string[],
  route: { requires: readonly Permission[] },
) {
  if (route.requires.length === 0) return true
  if (hasAllPermission(permissions)) return true

  return hasAnyPermission(permissions, route.requires)
}

/**
 * `held` 是否涵蓋 `requested` 的每一個權限 —— 「不能給出自己沒有的權限」的前端版本。
 *
 * **`held` 必須是展開相依之後的集合** (`GET /users/me` 回的就是), 前端不認得相依關係。
 * 後端的同一條規則在 `shared/auth/permissions.py` 的 `PermissionResolver.covers`, 這裡只決定
 * 按鈕要不要出現, 擋不擋得住由後端負責。
 */
export function coversPermissions(held: readonly string[], requested: readonly string[]) {
  return hasAllPermission(held) || requested.every((permission) => held.includes(permission))
}
