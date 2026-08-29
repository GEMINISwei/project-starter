import { redirect } from "next/navigation"
import { getCurrentUser } from "@/shared/session/current-user.server"
import { canAccessRoute } from "@/shared/access/permissions"
import { ADMIN_ROUTES } from "@/config/routes"

/**
 * `(admin)` route group 的存取控制。
 *
 * 判斷依據是「有沒有任何一條 admin 區路由的權限」，而不是「是不是超級管理者」，讓前端
 * 與後端共用同一套細粒度權限模型。
 *
 * 每個頁面自己還會再檢查一次它需要的權限（例如角色編輯頁要 roles:update），
 * 這一層只負責擋掉「整個管理區都不該看到」的人。真正的授權在後端。
 */
export default async function AdminLayout({ children }: React.PropsWithChildren) {
  const { data } = await getCurrentUser()
  const permissions = data?.permissions ?? []

  const canAccessAnyAdminRoute = ADMIN_ROUTES.some((route) => canAccessRoute(permissions, route))
  if (!canAccessAnyAdminRoute) {
    redirect("/")
  }

  return children
}
