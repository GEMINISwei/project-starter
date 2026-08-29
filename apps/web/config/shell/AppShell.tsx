"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { LogOut } from "lucide-react"
import { ICON_SIZE } from "@/shared/ui"
import { canAccessRoute } from "@/shared/access/permissions"
import { useLocale, useT } from "@/shared/i18n/context"
import { usePublicConfig } from "@/shared/runtime/context"
import { appMessages } from "@/config/i18n"
import { logout } from "@/config/session-actions"
import { PROTECTED_ROUTES } from "@/config/routes"
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
  nickname: string
  userRole: string
  permissions: readonly string[]
  children: React.ReactNode
}

export default function AppShell({ nickname, userRole, permissions, children }: AppShellProps) {
  const t = useT(appMessages)
  const locale = useLocale()
  const { systemName } = usePublicConfig()
  const avatarText = nickname[0]?.toUpperCase() ?? "?"
  // 與 (admin)/layout.tsx 用同一個 canAccessRoute，導覽列與實際能不能進去必然一致。
  const visibleRoutes = PROTECTED_ROUTES.filter((route) => canAccessRoute(permissions, route))

  function renderNav(variant: "sidebar" | "bottom") {
    const size = variant === "sidebar" ? 16 : 21

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
        </div>

        <nav className={styles.sidebarNav} aria-label={t("mainNav")}>
          <span className={styles.navSectionLabel}>{t("navSection")}</span>
          {renderNav("sidebar")}
        </nav>

        {nickname && (
          <div className={styles.sidebarFooter}>
            <div className={styles.sidebarUser}>
              <div className={styles.userAvatar} aria-label={nickname} title={nickname}>
                {avatarText}
              </div>
              <div className={styles.userDetails}>
                <span className={styles.userName}>{nickname}</span>
                <span className={styles.userRole}>{userRole}</span>
              </div>
              <form action={logout}>
                <button type="submit" className={styles.logoutIconBtn} aria-label={t("logout")} title={t("logout")}>
                  <LogOut size={ICON_SIZE.sm} />
                </button>
              </form>
            </div>
          </div>
        )}
      </aside>

      <nav className={styles.bottomNavigation} aria-label={t("mobileNav")}>
        {renderNav("bottom")}
      </nav>

      {children}
    </div>
  )
}
