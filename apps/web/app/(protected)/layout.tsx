import { redirect } from "next/navigation"
import { getCurrentUser } from "@/shared/session/current-user.server"
import { getT } from "@/shared/i18n/locale.server"
import { appMessages } from "@/config/i18n"
import WSManager from "@/config/realtime/WSManager"
import AppShell from "@/config/shell/AppShell"
import { PushNotificationManager } from "@/modules/push/public.client"
import styles from "@/config/shell/shell.module.css"

export default async function ProtectedLayout({
  children,
}: React.PropsWithChildren) {
  const t = await getT(appMessages)
  const { res, data, isSuperUser } = await getCurrentUser()

  if (res.status !== "success" || !data) {
    redirect("/login?reason=session-expired")
  }

  const userNickname = typeof data.nickname === "string" ? data.nickname : ""
  const userRole = isSuperUser ? t("roleSuperAdmin") : t("roleUser")

  return (
    <AppShell
      nickname={userNickname}
      userRole={userRole}
      permissions={data.permissions}
    >
      <PushNotificationManager />
      {/* 刻意不把 access_token 傳進來：那會讓它被序列化進 RSC payload 送到瀏覽器，
          等於架空 httpOnly cookie。WSManager 自己去換短效 ticket。 */}
      <WSManager />
      <main className={styles.main}>
        {children}
      </main>
    </AppShell>
  )
}
