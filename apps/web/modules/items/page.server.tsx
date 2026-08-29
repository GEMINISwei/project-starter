/**
 * **範例模組** —— 示範一個列表頁該怎麼組。用不到時整包刪除，見 docs/architecture.md「移除 module」。
 *
 * 這裡示範的慣例：
 * - 分頁參數用 `parsePagination()` 解析，資料用 `fetchPaginatedList()` 抓
 * - 頁面自己用 `canAccessRoute()` 再擋一次（layout 只做粗篩，使用者仍可能手打網址）
 * - 資料抓取留在 Server Component，互動狀態交給底下的 `ItemsView`（client）
 */

import { redirect } from "next/navigation"
import { getCurrentUser } from "@/shared/session/current-user.server"
import { fetchPaginatedList, parsePagination } from "@/shared/pagination/fetch.server"
import { parseBooleanFilter } from "@/shared/pagination/query"
import { canAccessRoute } from "@/shared/access/permissions"
import { getT } from "@/shared/i18n/locale.server"
import { itemsMessages } from "./i18n"
import { ITEMS_ROUTE } from "./manifest"
import ItemsView from "./ui/ItemsView"

export async function generateMetadata() {
  return { title: (await getT(itemsMessages))("pageTitle") }
}

const ITEMS_PAGE_LIMIT = 10

// 轉出給 route adapter 當 props 型別用，adapter 才不必把 searchParams 的形狀再抄一次。
export type ItemsPageProps = {
  searchParams?: Promise<{
    cursor?: string
    direction?: string
    seq?: string
    name?: string
    is_disabled?: string
  }>
}

export default async function ItemsPage({ searchParams }: ItemsPageProps) {
  const t = await getT(itemsMessages)
  const { data: currentUser } = await getCurrentUser()
  if (!canAccessRoute(currentUser?.permissions ?? [], ITEMS_ROUTE)) {
    redirect("/")
  }

  const params = await searchParams
  const { cursor, direction, seq } = parsePagination(params)
  const name = params?.name ?? ""
  const isDisabled = parseBooleanFilter(params?.is_disabled)

  const { items, meta, errorMessage } = await fetchPaginatedList({
    url: "/items/",
    limit: ITEMS_PAGE_LIMIT,
    cursor,
    direction,
    query: {
      ...(name ? { name } : {}),
      ...(isDisabled ? { is_disabled: isDisabled } : {}),
    },
    errorFallback: t("listFailed"),
  })

  return (
    <ItemsView
      items={items}
      meta={meta}
      seq={seq}
      limit={ITEMS_PAGE_LIMIT}
      currentUser={currentUser}
      errorMessage={errorMessage}
      filters={{ name, isDisabled }}
    />
  )
}
