import { redirect } from "next/navigation"
import { getCurrentUser } from "@/modules/auth/public.server"
import AreaLayout from "@/config/shell/AreaLayout"

/**
 * 管理區 (使用者、角色) 只開放給超級管理者。角色上的權限是給一般帳號的業務功能用的,
 * 沒有任何一個權限能打開這一區。
 *
 * 真正的授權在後端 (這些端點都要求 `Permission.ALL`)。
 */
export default async function AdminLayout({ children }: React.PropsWithChildren) {
  const { isSuperUser } = await getCurrentUser()

  if (!isSuperUser) {
    redirect("/")
  }

  return <AreaLayout area="admin">{children}</AreaLayout>
}
