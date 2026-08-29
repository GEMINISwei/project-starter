import { redirect } from "next/navigation"
import { getCurrentUser } from "@/shared/session/current-user.server"
import { fetchPaginatedList, parsePagination } from "@/shared/pagination/fetch.server"
import { parseBooleanFilter } from "@/shared/pagination/query"
import { canAccessRoute } from "@/shared/access/permissions"
import { getT } from "@/shared/i18n/locale.server"
import { rolesMessages } from "./i18n"
import { ROLES_ROUTE } from "./manifest"
import RolesView from "./ui/RolesView"

export async function generateMetadata() {
  return { title: (await getT(rolesMessages))("pageTitle") }
}

const ROLES_PAGE_LIMIT = 10

export type RolesPageProps = {
  searchParams?: Promise<{
    cursor?: string
    direction?: string
    seq?: string
    name?: string
    is_disabled?: string
  }>
}

export default async function RolesPage({ searchParams }: RolesPageProps) {
  const t = await getT(rolesMessages)
  // 同 users/page.server.tsx：管理區的 layout 只做粗篩，本頁需要的權限在這裡再確認一次。
  const { data: accessCheck } = await getCurrentUser()
  if (!canAccessRoute(accessCheck?.permissions ?? [], ROLES_ROUTE)) {
    redirect("/")
  }

  const params = await searchParams
  const { cursor, direction, seq } = parsePagination(params)
  const name = params?.name ?? ""
  const isDisabled = parseBooleanFilter(params?.is_disabled)

  // getCurrentUser() 有 React `cache()`，同一次 render 內與 layout 共用同一筆結果。
  const [rolesResult, { data: currentUser }] = await Promise.all([
    fetchPaginatedList({
      url: "/roles/",
      limit: ROLES_PAGE_LIMIT,
      cursor,
      direction,
      query: {
        ...(name ? { name } : {}),
        ...(isDisabled ? { is_disabled: isDisabled } : {}),
      },
      errorFallback: t("listFailed"),
    }),
    getCurrentUser(),
  ])
  const { items: roles, meta, errorMessage } = rolesResult

  return (
    <RolesView
      roles={roles}
      meta={meta}
      seq={seq}
      limit={ROLES_PAGE_LIMIT}
      currentUser={currentUser}
      errorMessage={errorMessage}
      filters={{ name, isDisabled }}
    />
  )
}
