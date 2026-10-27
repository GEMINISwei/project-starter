import { redirect } from "next/navigation"
import { getCurrentUser } from "@/modules/auth/public.server"
import { LOGIN_REDIRECT_REASONS, loginUrl } from "@/shared/session/login-contract"

/**
 * 受保護區的登入檢查。外殼由底下的 `(user)`/`admin/` 各自組裝, 兩區的導覽不同。
 * `getCurrentUser()` 有 `cache()`, 這裡與子 layout 各呼叫一次也只打一次 API。
 */
export default async function ProtectedLayout({ children }: React.PropsWithChildren) {
  const { res, data } = await getCurrentUser()

  if (res.status !== "success" || !data) {
    redirect(loginUrl(LOGIN_REDIRECT_REASONS.sessionExpired))
  }

  return children
}
