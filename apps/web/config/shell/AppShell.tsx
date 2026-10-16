"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useTransition } from "react"
import { ChevronsUpDown, House, LayoutDashboard, LogOut, Settings, type LucideIcon } from "lucide-react"
import { ICON_SIZE, Menu, type MenuItem } from "@/shared/ui"
import { useLocale, useT } from "@/shared/i18n/context"
import { usePublicConfig } from "@/shared/runtime/context"
import { appMessages } from "@/config/i18n"
import { logout } from "@/config/session-actions"
import { navRoutes } from "@/config/routes"
import type { RouteArea } from "@/shared/module"
import { type AccountMenuEntry, type AccountMenuLabel, getAccountMenuEntries } from "./account-menu"
import { NAV_ICONS } from "./nav-icons"
import styles from "./shell.module.css"

type NavLinkProps = {
  href: string
  icon: React.ReactNode
  label: string
  variant: "sidebar" | "bottom"
}

function NavLink({ href, icon, label, variant }: NavLinkProps) {
  const pathname = usePathname()
  const isActive = pathname === href || pathname.startsWith(`${href}/`)
  const linkClass = variant === "sidebar" ? styles.navLink : styles.bottomNavItem
  const activeClass = variant === "sidebar" ? styles.navLinkActive : styles.bottomNavItemActive

  return (
    <Link
      href={href}
      className={`${linkClass} ${isActive ? activeClass : ""}`}
      title={label}
      prefetch={false}
    >
      {icon}
      <span className={variant === "sidebar" ? styles.navLinkLabel : undefined}>{label}</span>
    </Link>
  )
}

type AppShellProps = {
  area: RouteArea
  nickname: string
  userRole: string
  permissions: readonly string[]
  children: React.ReactNode
}

// `Record<AccountMenuLabel, …>` 是窮盡的: 選單多一種項目卻沒給圖示會編譯失敗。
const ENTRY_ICONS: Record<AccountMenuLabel, LucideIcon> = {
  goAdminArea: LayoutDashboard,
  goUserArea: House,
  accountSettings: Settings,
  logout: LogOut,
}

/** 頭像選單: 側欄底部與手機底部導覽共用同一份項目, 只差觸發按鈕長什麼樣子。 */
function useAccountMenuItems(area: RouteArea, permissions: readonly string[]): MenuItem[] {
  const t = useT(appMessages)
  const router = useRouter()
  const [, startTransition] = useTransition()

  function toItem(entry: AccountMenuEntry): MenuItem {
    const Icon = ENTRY_ICONS[entry.label]
    return {
      icon: <Icon size={ICON_SIZE.sm} />,
      label: t(entry.label),
      onClick: entry.kind === "logout"
        ? () => startTransition(() => logout())
        : () => router.push(entry.href),
    }
  }

  return getAccountMenuEntries(area, permissions).map(toItem)
}

export default function AppShell({
  area, nickname, userRole, permissions, children,
}: AppShellProps) {
  const t = useT(appMessages)
  const locale = useLocale()
  const { systemName } = usePublicConfig()
  const avatarText = nickname[0]?.toUpperCase() ?? "?"
  const visibleRoutes = navRoutes(area, permissions)
  const accountItems = useAccountMenuItems(area, permissions)
  const avatar = <span className={styles.userAvatar} aria-hidden>{avatarText}</span>

  function renderNav(variant: "sidebar" | "bottom") {
    // 底部導覽是手指點的, 圖示比側欄大一階。
    const size = variant === "sidebar" ? ICON_SIZE.sm : ICON_SIZE.md

    return visibleRoutes.map((route) => {
      const Icon = NAV_ICONS[route.navIcon]

      return (
        <NavLink
          key={route.path}
          variant={variant}
          href={route.path}
          icon={<Icon size={size} />}
          label={route.label[locale]}
        />
      )
    })
  }

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.sidebarLogo}>
          <span className={styles.sidebarWordmark}>{systemName}</span>
          {/* 切換區域收進頭像選單之後, 這是唯一一眼看得出「現在在後台」的地方。 */}
          {area === "admin" && <span className={styles.areaBadge}>{t("adminAreaBadge")}</span>}
        </div>

        <nav className={styles.sidebarNav} aria-label={t("mainNav")}>
          {/* 一般帳號目前沒有任何導覽項目 (設定在頭像選單裡), 不要留一個底下空空的標題。 */}
          {visibleRoutes.length > 0 && (
            <span className={styles.navSectionLabel}>
              {t(area === "admin" ? "navSectionAdmin" : "navSection")}
            </span>
          )}
          {renderNav("sidebar")}
        </nav>

        {nickname && (
          <div className={styles.sidebarFooter}>
            <Menu
              placement="above"
              fullWidth
              triggerLabel={t("accountMenu")}
              triggerClassName={styles.sidebarUser}
              items={accountItems}
              trigger={
                <>
                  {avatar}
                  <span className={styles.userDetails}>
                    <span className={styles.userName}>{nickname}</span>
                    <span className={styles.userRole}>{userRole}</span>
                  </span>
                  <ChevronsUpDown size={ICON_SIZE.sm} className={styles.userMenuIcon} aria-hidden />
                </>
              }
            />
          </div>
        )}
      </aside>

      <nav className={styles.bottomNavigation} aria-label={t("mobileNav")}>
        {renderNav("bottom")}
        {/* 手機沒有側欄: 切換區域與登出都在這一格的選單裡。 */}
        <Menu
          placement="above"
          fullWidth
          triggerLabel={t("accountMenu")}
          triggerClassName={styles.bottomNavItem}
          items={accountItems}
          trigger={
            <>
              <span className={styles.bottomNavAvatar} aria-hidden>{avatarText}</span>
              <span>{t("account")}</span>
            </>
          }
        />
      </nav>

      {children}
    </div>
  )
}
