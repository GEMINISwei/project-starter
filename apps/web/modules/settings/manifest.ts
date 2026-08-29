import type { ModuleManifest, ProtectedRoute } from "@/shared/module"

export const SETTINGS_ROUTE = {
  path: "/settings", label: { zh: "設定", en: "Settings" }, group: "general", requires: [], navIcon: "settings",
} as const satisfies ProtectedRoute

export const SETTINGS_MODULE = {
  name: "settings",
  protectedRoutes: [SETTINGS_ROUTE],
} as const satisfies ModuleManifest
