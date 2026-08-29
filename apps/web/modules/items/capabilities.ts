import { hasPermission } from "@/shared/access/permissions"

export function getItemCapabilities(permissions: readonly string[]) {
  return {
    canCreateItem: hasPermission(permissions, "items:create"),
    canUpdateItem: hasPermission(permissions, "items:update"),
    canDeleteItem: hasPermission(permissions, "items:delete"),
  }
}
