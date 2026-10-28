"use server"

import { redirect } from "next/navigation"
import { apiPost } from "@/shared/api/request.server"
import { isRedirectError } from "@/shared/api/redirect"
import { clearAccessTokenCookie } from "@/shared/session/access-token.server"
import { LOGIN_PATH } from "@/shared/session/login-contract"

export async function logout() {
  // 先請後端撤銷這個帳號所有裝置的 session, 再刪 cookie。只刪 cookie 的話, 已經被複製出去的
  // token 到期前仍然有效 (見 docs/features/session.md〈撤銷〉)。
  try {
    await apiPost({ url: "/users/me/logout" })
  } catch (err) {
    // token 早就失效時, request 會清掉 cookie 並導向「登入逾時」的登入頁。登出本來就要去登入頁,
    // 改走下面的一般導向, 免得剛按下登出的人看到「登入已逾時」。
    if (!isRedirectError(err)) throw err
  }

  await clearAccessTokenCookie()
  redirect(LOGIN_PATH)
}
