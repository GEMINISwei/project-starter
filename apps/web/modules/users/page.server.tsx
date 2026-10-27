import "server-only"
import { getApiResponseErrorMessage } from "@/shared/api/error"
import { getApiListData } from "@/shared/api/response"
import { getCurrentUser } from "@/modules/auth/public.server"
import { getRoleOptions } from "@/modules/roles/public.server"
import { fetchPaginatedList, parsePagination } from "@/shared/pagination/fetch.server"
import { parseBooleanFilter } from "@/shared/pagination/query"
import { getT } from "@/shared/i18n/locale.server"
import { usersMessages } from "./i18n"
import UsersView from "./ui/UsersView"

export async function generateMetadata() {
  return { title: (await getT(usersMessages))("pageTitle") }
}

const USERS_PAGE_LIMIT = 10

export type UsersPageProps = {
  searchParams?: Promise<{
    cursor?: string
    direction?: string
    seq?: string
    name?: string
    role_id?: string
    is_disabled?: string
  }>
}

export default async function UsersPage({ searchParams }: UsersPageProps) {
  const t = await getT(usersMessages)
  const params = await searchParams
  const { cursor, direction, seq } = parsePagination(params)
  const name = params?.name ?? ""
  const roleId = params?.role_id ?? ""
  const isDisabled = parseBooleanFilter(params?.is_disabled)

  const [usersResult, currentUserResult, rolesRes] = await Promise.all([
    fetchPaginatedList({
      url: "/users/",
      limit: USERS_PAGE_LIMIT,
      cursor,
      direction,
      query: {
        ...(name ? { name } : {}),
        ...(roleId ? { role_id: roleId } : {}),
        ...(isDisabled ? { is_disabled: isDisabled } : {}),
      },
      errorFallback: t("listFailed"),
    }),
    getCurrentUser(),
    // 這裡要的是「填下拉選單用的完整角色清單」, 所以走非分頁的那一份。
    getRoleOptions(),
  ])

  const { items: users, meta, errorMessage } = usersResult
  const currentUser = currentUserResult.data
  const roles = getApiListData(rolesRes)

  const rolesErrorMessage = rolesRes.status === "success"
    ? ""
    : getApiResponseErrorMessage(rolesRes, t("rolesFailed"))

  return (
    <UsersView
      users={users}
      meta={meta}
      seq={seq}
      limit={USERS_PAGE_LIMIT}
      currentUser={currentUser}
      roles={roles}
      errorMessage={errorMessage}
      rolesErrorMessage={rolesErrorMessage}
      filters={{ name, roleId, isDisabled }}
    />
  )
}
