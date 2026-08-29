import type { ModuleManifest, ProtectedRoute } from "@/shared/module"

export const USERS_ROUTE = {
  path: "/users", label: { zh: "使用者", en: "Users" }, group: "admin", requires: ["users:read"], navIcon: "users",
} as const satisfies ProtectedRoute

export const USERS_MODULE = {
  name: "users",
  protectedRoutes: [USERS_ROUTE],
} as const satisfies ModuleManifest
