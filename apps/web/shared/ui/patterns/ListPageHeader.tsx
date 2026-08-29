"use client"

import { useRouter } from "next/navigation"
import { Filter, Plus, RefreshCw } from "lucide-react"
import { useT } from "@/shared/i18n/context"
import { Button, Flex } from "../primitives"
import { ICON_SIZE } from "../internals"
import { usePaginationResetHref } from "../pagination"
import { uiMessages } from "../i18n"
import PageHeader from "./PageHeader"

type ListPageHeaderProps = {
  title: string
  subtitle: string
  showReset: boolean
  onFilter: () => void
  createAction?: { label: string; onClick: () => void }
}

export default function ListPageHeader({
  title,
  subtitle,
  showReset,
  onFilter,
  createAction,
}: ListPageHeaderProps) {
  const t = useT(uiMessages)
  const router = useRouter()
  const resetHref = usePaginationResetHref()

  return (
    <PageHeader
      title={title}
      subtitle={subtitle}
      actions={(
        <Flex gap={2}>
          {showReset && (
            <Button
              variant="outlined"
              icon={<RefreshCw size={ICON_SIZE.sm} />}
              text={t("refresh")}
              onClick={() => router.push(resetHref)}
            />
          )}
          <Button
            variant="outlined"
            icon={<Filter size={ICON_SIZE.sm} />}
            text={t("filter")}
            onClick={onFilter}
          />
          {createAction && (
            <Button
              icon={<Plus size={ICON_SIZE.md} />}
              text={createAction.label}
              onClick={createAction.onClick}
            />
          )}
        </Flex>
      )}
      mobileActions={[
        createAction && {
          icon: <Plus size={ICON_SIZE.sm} />,
          label: createAction.label,
          onClick: createAction.onClick,
        },
        { icon: <Filter size={ICON_SIZE.sm} />, label: t("filter"), onClick: onFilter },
        showReset && {
          icon: <RefreshCw size={ICON_SIZE.sm} />,
          label: t("refresh"),
          onClick: () => router.push(resetHref),
        },
      ]}
    />
  )
}
