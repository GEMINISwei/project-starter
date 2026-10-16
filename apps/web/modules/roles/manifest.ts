import type { ModuleManifest, ProtectedRoute } from "@/shared/module"

/** 管理區是真正的路徑段, 所以模組內的連結都要帶 `/admin` 前綴。 */
export const ROLES_PATH = "/admin/roles"

const ROLES_ROUTE = {
  path: ROLES_PATH, label: { zh: "角色", en: "Roles" }, group: "admin", requires: ["*"], navIcon: "roles", showInNav: true,
} as const satisfies ProtectedRoute

export const ROLES_MODULE = {
  name: "roles",
  protectedRoutes: [ROLES_ROUTE],
} as const satisfies ModuleManifest
