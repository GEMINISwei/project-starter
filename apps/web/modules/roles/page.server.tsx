import "server-only"
import { fetchPaginatedList, parsePagination } from "@/shared/pagination/fetch.server"
import { parseBooleanFilter } from "@/shared/pagination/query"
import { getT } from "@/shared/i18n/locale.server"
import { rolesMessages } from "./i18n"
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
  const params = await searchParams
  const { cursor, direction, seq } = parsePagination(params)
  const name = params?.name ?? ""
  const isDisabled = parseBooleanFilter(params?.is_disabled)

  const { items: roles, meta, errorMessage } = await fetchPaginatedList({
    url: "/roles/",
    limit: ROLES_PAGE_LIMIT,
    cursor,
    direction,
    query: {
      ...(name ? { name } : {}),
      ...(isDisabled ? { is_disabled: isDisabled } : {}),
    },
    errorFallback: t("listFailed"),
  })

  return (
    <RolesView
      roles={roles}
      meta={meta}
      seq={seq}
      limit={ROLES_PAGE_LIMIT}
      errorMessage={errorMessage}
      filters={{ name, isDisabled }}
    />
  )
}
