"use client"

import type { ReactNode } from "react"
import Link from "next/link"
import { usePathname, useSearchParams } from "next/navigation"
import { ChevronLeft, ChevronRight } from "lucide-react"
import type { ApiListMeta } from "@/shared/api/response"
import { useT } from "@/shared/i18n/context"
import { ICON_SIZE } from "./internals"
import styles from "./styles/primitives.module.css"
import { cls } from "./internals"
import { uiMessages } from "./i18n"
import { Flex } from "./primitives"

type PaginationProps = { meta: ApiListMeta; seq: number; limit: number; summary?: ReactNode }

export function usePaginationResetHref(): string {
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const params = new URLSearchParams(searchParams.toString())
  params.delete("cursor")
  params.delete("direction")
  params.delete("seq")
  const query = params.toString()
  return query ? `${pathname}?${query}` : pathname
}

export function Pagination({ meta, seq, limit, summary }: PaginationProps) {
  const t = useT(uiMessages)
  const pathname = usePathname()
  const searchParams = useSearchParams()
  const totalPages =
    meta.totalCount != null ? Math.max(1, Math.ceil(meta.totalCount / limit)) : null
  function buildHref(overrides: Record<string, string | null>) {
    const params = new URLSearchParams(searchParams.toString())
    for (const [key, value] of Object.entries(overrides)) {
      if (value === null) params.delete(key)
      else params.set(key, value)
    }
    const query = params.toString()
    return query ? `${pathname}?${query}` : pathname
  }
  function hrefFor(direction: "next" | "prev", cursor: string) {
    return buildHref({ cursor, direction, seq: String(direction === "next" ? seq + 1 : seq - 1) })
  }
  return (
    <div className={styles.paginationBar}>
      <Flex gap={2} className={styles.paginationButtons}>
        {meta.hasPrevious && meta.prevCursor ? (
          <Link href={hrefFor("prev", meta.prevCursor)} className={styles.paginationLink}>
            <ChevronLeft size={ICON_SIZE.sm} aria-hidden="true" /> {t("prevPage")}
          </Link>
        ) : (
          <span className={cls(styles.paginationLink, styles.paginationLinkDisabled)} aria-disabled="true">
            <ChevronLeft size={ICON_SIZE.sm} aria-hidden="true" /> {t("prevPage")}
          </span>
        )}
        {meta.hasNext && meta.nextCursor ? (
          <Link href={hrefFor("next", meta.nextCursor)} className={styles.paginationLink}>
            {t("nextPage")} <ChevronRight size={ICON_SIZE.sm} aria-hidden="true" />
          </Link>
        ) : (
          <span className={cls(styles.paginationLink, styles.paginationLinkDisabled)} aria-disabled="true">
            {t("nextPage")} <ChevronRight size={ICON_SIZE.sm} aria-hidden="true" />
          </span>
        )}
      </Flex>
      <div className={styles.paginationSummary}>
        <span className={styles.paginationCurrent}>
          {totalPages
            ? t("pageOf", { seq, total: totalPages })
            : t("page", { seq })}
          {summary && ` (${summary})`}
        </span>
      </div>
    </div>
  )
}
