import { hasAllPermission, hasPermission } from "@/shared/access/permissions"
import type { Translator } from "@/shared/i18n/dictionary"
import { getRoleDisplayName, type rolesMessages } from "@/modules/roles/public.client"
import type { usersMessages } from "./i18n"
import type { RoleInfo, UserInfo } from "./types"

type UsersT = Translator<(typeof usersMessages)["zh"]>
type RolesT = Translator<(typeof rolesMessages)["zh"]>

/** 這個使用者身上是否掛著任何一個擁有最高權限的角色。 */
export function isSuperAdminUser(user: UserInfo, roles: RoleInfo[]) {
  return user.role_ids.some((roleId) => {
    const role = roles.find((item) => item.id === roleId)
    return role ? hasAllPermission(role.permissions) : false
  })
}

/** 使用者的角色名稱；已停用的角色帶後綴，一個角色都沒有時回傳「未指派」。 */
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

export function getUserCapabilities(permissions: readonly string[]) {
  return {
    isSuperUser: hasAllPermission(permissions),
    canCreateUser: hasPermission(permissions, "users:create"),
    canUpdateAnyUser: hasPermission(permissions, "users:update:any"),
    canUpdateOwnUser: hasPermission(permissions, "users:update:own"),
    canDeleteUser: hasPermission(permissions, "users:delete"),
  }
}
