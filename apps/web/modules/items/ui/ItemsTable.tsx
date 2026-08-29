"use client"

import { Pencil, Trash2 } from "lucide-react"
import { ICON_SIZE } from "@/shared/ui"
import {
  ActionMenu,
  ErrorState,
  ListTableCard,
  Pagination,
  StatusBadge,
  Surface,
  TableRow,
} from "@/shared/ui"
import type { ApiListMeta } from "@/shared/api/response"
import { useT } from "@/shared/i18n/context"
import { itemsMessages } from "../i18n"
import { getItemCapabilities } from "../capabilities"
import type { CurrentUser, ItemInfo } from "../types"
import styles from "./items.module.css"

type ItemsTableProps = {
  items: ItemInfo[]
  meta: ApiListMeta
  seq: number
  limit: number
  currentUser: CurrentUser | null
  errorMessage: string
  onEdit: (item: ItemInfo) => void
  onDelete: (item: ItemInfo) => void
}

/**
 * 項目列表本體（錯誤狀態、表格、分頁）。
 *
 * 字典與權限在這裡自己算，不由 `ItemsView` 傳進來 —— 兩者都是 `currentUser` 的純推導。
 */
export default function ItemsTable({
  items,
  meta,
  seq,
  limit,
  currentUser,
  errorMessage,
  onEdit,
  onDelete,
}: ItemsTableProps) {
  const t = useT(itemsMessages)
  const { canUpdateItem, canDeleteItem } = getItemCapabilities(currentUser?.permissions ?? [])

  if (errorMessage) {
    return (
      <Surface>
        <ErrorState>{errorMessage}</ErrorState>
      </Surface>
    )
  }

  return (
    <>
      <ListTableCard
        headers={[
          t("colName"),
          t("colDescription"),
          t("colCreatedBy"),
          t("colStatus"),
          t("colActions"),
        ]}
        isEmpty={items.length === 0}
        emptyText={t("empty")}
      >
        {items.map((item) => (
          <TableRow key={item.id}>
            <td data-label={t("colName")}>{item.name}</td>
            <td data-label={t("colDescription")}>
              <span className={styles.description}>{item.description || "—"}</span>
            </td>
            {/* created_by_nickname 不是 items 表的欄位，是 repository 用 $lookup 補上的 */}
            <td data-label={t("colCreatedBy")}>{item.created_by_nickname || "—"}</td>
            <td data-label={t("colStatus")}>
              <StatusBadge
                label={item.is_disabled ? t("statusDisabled") : t("statusActive")}
                variant={item.is_disabled ? "muted" : "success"}
              />
            </td>
            <td data-label={t("colActions")}>
              <ActionMenu
                items={[
                  canUpdateItem && {
                    icon: <Pencil size={ICON_SIZE.sm} />,
                    label: t("edit"),
                    onClick: () => onEdit(item),
                  },
                  canDeleteItem && {
                    icon: <Trash2 size={ICON_SIZE.sm} />,
                    label: t("delete"),
                    onClick: () => onDelete(item),
                  },
                ]}
              />
            </td>
          </TableRow>
        ))}
      </ListTableCard>
      <Pagination
        meta={meta}
        seq={seq}
        limit={limit}
        summary={t("summary", { count: meta.totalCount ?? 0 })}
      />
    </>
  )
}
