/** 路由的組裝點。這份檔案會被 proxy.ts 載入，所以只能用 Edge runtime 跑得動的東西。 */

import type { ModuleManifest, ProtectedRoute } from "@/shared/module"
import { AUTH_MODULE } from "@/modules/auth/manifest"
import { ITEMS_MODULE } from "@/modules/items/manifest"
import { PUSH_MODULE } from "@/modules/push/manifest"
import { ROLES_MODULE } from "@/modules/roles/manifest"
import { SETTINGS_MODULE } from "@/modules/settings/manifest"
import { USERS_MODULE } from "@/modules/users/manifest"

/**
 * 前端唯一的模組啟用清單。底下的執行期陣列與型別聯集**全部**從這一份推導 —— 新增模組只要在
 * 這裡加一行，`PROTECTED_ROUTES`、`ProtectedRoutePath`、`NavIconKey` 就會自動跟上。陣列順序
 * 同時決定側欄導覽的顯示順序。
 *
 * `as const satisfies` 兩個都要：`satisfies` 檢查每個 manifest 的形狀，`as const` 保住字面值
 * 型別 —— 少了它，路徑與圖示代號會退化成 `string`，編譯期保護就沒了。
 */
export const ENABLED_MODULES = [
  AUTH_MODULE,
  USERS_MODULE,
  ROLES_MODULE,
  ITEMS_MODULE,
  SETTINGS_MODULE,
  PUSH_MODULE,
] as const satisfies readonly ModuleManifest[]

/** 啟用清單裡所有路由的聯集。沒有路由的模組貢獻 `never`，會自動從聯集消失。 */
type EnabledRoute = (typeof ENABLED_MODULES)[number]["protectedRoutes"][number]

// 型別標成 `EnabledRoute` 而不是 `ProtectedRoute`：後者會把 path 與 navIcon 放寬成
// `string`，那樣 `NAV_ICONS` 的窮盡檢查與 `getRoute()` 的路徑檢查都會失效。
export const PROTECTED_ROUTES: readonly EnabledRoute[] = ENABLED_MODULES.flatMap(
  (module) => [...module.protectedRoutes],
)

export type ProtectedRoutePath = EnabledRoute["path"]

export type NavIconKey = EnabledRoute["navIcon"]

export const ADMIN_ROUTES = PROTECTED_ROUTES.filter((route) => route.group === "admin")

export function getRoute(path: ProtectedRoutePath): ProtectedRoute {
  const route = PROTECTED_ROUTES.find((item) => item.path === path)
  if (!route) throw new Error(`Undefined protected route: ${path}`)
  return route
}

export function isProtectedPathname(pathname: string): boolean {
  return PROTECTED_ROUTES.some(
    (route) => pathname === route.path || pathname.startsWith(`${route.path}/`),
  )
}
