import type { ModuleManifest, ProtectedRoute } from "@/shared/module"

export const ROLES_ROUTE = {
  path: "/roles", label: { zh: "角色", en: "Roles" }, group: "admin", requires: ["roles:read"], navIcon: "roles",
} as const satisfies ProtectedRoute

export const ROLES_MODULE = {
  name: "roles",
  protectedRoutes: [ROLES_ROUTE],
} as const satisfies ModuleManifest
