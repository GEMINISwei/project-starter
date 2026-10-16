import { getCurrentUser } from "@/modules/auth/public.server"
import { getT } from "@/shared/i18n/locale.server"
import type { RouteArea } from "@/shared/module"
import { appMessages } from "@/config/i18n"
import AppShell from "./AppShell"
import styles from "./shell.module.css"

type AreaLayoutProps = {
  area: RouteArea
  children: React.ReactNode
}

/**
 * `admin/`/`(user)` 兩區共用的外殼組裝; 登入檢查在上一層的 `(protected)/layout.tsx`。
 *
 * 頁面的 `<main>` 地標由這裡提供, 所以這兩區的頁面不要再渲染 `<main>` (`tests/architecture.test.ts` 擋)。
 */
export default async function AreaLayout({ area, children }: AreaLayoutProps) {
  const t = await getT(appMessages)
  const { data, isSuperUser } = await getCurrentUser()

  return (
    <AppShell
      area={area}
      nickname={data?.nickname ?? ""}
      userRole={isSuperUser ? t("roleSuperAdmin") : t("roleUser")}
      permissions={data?.permissions ?? []}
    >
      <main className={styles.main}>{children}</main>
    </AppShell>
  )
}
