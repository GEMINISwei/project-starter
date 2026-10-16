import { hasAllPermission } from "@/shared/access/permissions"
import type { Translator } from "@/shared/i18n/dictionary"
import { getRoleDisplayName, type rolesMessages } from "@/modules/roles/public.client"
import type { usersMessages } from "./i18n"
import type { RoleInfo, UserInfo } from "./types"

// 這個模組的畫面只有超級管理者進得來 (`admin/layout.tsx`), 所以這裡不判斷操作者的權限,
// 只留不論是誰都不該做的事。

type UsersT = Translator<(typeof usersMessages)["zh"]>
type RolesT = Translator<(typeof rolesMessages)["zh"]>

/** 這個使用者身上是否掛著任何一個擁有最高權限的角色。 */
export function isSuperAdminUser(user: UserInfo, roles: RoleInfo[]) {
  return user.role_ids.some((roleId) => {
    const role = roles.find((item) => item.id === roleId)
    return role ? hasAllPermission(role.permissions) : false
  })
}

/** 使用者的角色名稱; 已停用的角色帶後綴, 一個角色都沒有時回傳「未指派」。 */
export function formatRoleNames(
  user: UserInfo,
  roles: RoleInfo[],
  t: UsersT,
  roleT: RolesT,
): string {
  const names = user.role_ids
    .map((roleId) => {
      const role = roles.find((item) => item.id === roleId)
      if (!role) return null
      return role.is_disabled
        ? t("roleDisabledSuffix", { name: getRoleDisplayName(role, roleT) })
        : getRoleDisplayName(role, roleT)
    })
    .filter((name): name is string => Boolean(name))

  return names.length > 0 ? names.join(t("roleSeparator")) : t("roleUnassigned")
}

/**
 * 編輯對話框裡哪些欄位可以動: 不能改自己的角色、不能停用自己, 超級管理者帳號的角色與狀態都不能動。
 *
 * 與後端 `modules/users/service.py` 的保護規則同一組。
 */
export function getEditableUserFields(
  user: UserInfo,
  currentUserId: string | undefined,
  roles: RoleInfo[],
  hasRoleOptions: boolean,
) {
  const isSelf = user.id === currentUserId
  const isSuperAdmin = isSuperAdminUser(user, roles)
  return {
    canAssignRole: !isSelf && !isSuperAdmin && hasRoleOptions,
    canToggleStatus: !isSelf && !isSuperAdmin,
  }
}

/**
 * 編輯送出的 `role_ids`。選「未指派」要送空陣列 —— `undefined` 在後端是「不改角色」,
 * 畫面會說更新成功, 角色卻原封不動。
 *
 * 看不到角色欄位時一律不送, 送了會撞上後端的保護規則。
 */
export function roleIdsForUpdate(canAssignRole: boolean, selectedRoleId: string) {
  if (!canAssignRole) return undefined
  return selectedRoleId ? [selectedRoleId] : []
}

/**
 * 超級管理者帳號 (包含自己) 不能在後台重設密碼: 否則一位超管可以把其他超管鎖在系統外。
 * 能進後台的只有超管, 改自己的密碼走設定頁 (要驗舊密碼, 也不會被登出)。
 */
export function canResetPassword(user: UserInfo, roles: RoleInfo[]) {
  return !isSuperAdminUser(user, roles)
}

/** 這個角色能不能指派: 啟用中、不是超級管理者角色 (超管只能由 bootstrap 或 CLI 產生)。 */
export function isAssignableRole(role: RoleInfo) {
  return !role.is_disabled && !hasAllPermission(role.permissions)
}
