import type { ModuleManifest, ProtectedRoute } from "@/shared/module"

export const ITEMS_ROUTE = {
  path: "/items", label: { zh: "項目", en: "Items" }, group: "general", requires: ["items:read"], navIcon: "items",
} as const satisfies ProtectedRoute

export const ITEMS_MODULE = {
  name: "items",
  protectedRoutes: [ITEMS_ROUTE],
} as const satisfies ModuleManifest
