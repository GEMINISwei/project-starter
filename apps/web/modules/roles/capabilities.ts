import { hasPermission } from "@/shared/access/permissions"

export function getRoleCapabilities(permissions: readonly string[]) {
  return {
    canCreateRole: hasPermission(permissions, "roles:create"),
    canUpdateRole: hasPermission(permissions, "roles:update"),
  }
}
