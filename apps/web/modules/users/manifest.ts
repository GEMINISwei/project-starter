import type { ModuleManifest, ProtectedRoute } from "@/shared/module"

/** 管理區是真正的路徑段, 所以模組內的連結都要帶 `/admin` 前綴。 */
export const USERS_PATH = "/admin/users"

const USERS_ROUTE = {
  path: USERS_PATH, label: { zh: "使用者", en: "Users" }, group: "admin", requires: ["*"], navIcon: "users", showInNav: true,
} as const satisfies ProtectedRoute

export const USERS_MODULE = {
  name: "users",
  protectedRoutes: [USERS_ROUTE],
} as const satisfies ModuleManifest
