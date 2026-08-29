"use client"

import { useState } from "react"
import {
  Confirm,
  Container,
  FilterDialog,
  ListPageHeader,
  Notify,
  useActionSubmit,
  useListFeedback,
  useStatusFilterOptions,
} from "@/shared/ui"
import type { ApiListMeta } from "@/shared/api/response"
import { useT } from "@/shared/i18n/context"
import { itemsMessages } from "../i18n"
import { getItemCapabilities } from "../capabilities"
import type { CurrentUser, ItemFilters, ItemInfo } from "../types"
import { deleteItem } from "../actions"
import CreateItemDialog from "./CreateItemDialog"
import EditItemDialog from "./EditItemDialog"
import ItemsTable from "./ItemsTable"

type Dialog = "create" | "edit" | "delete" | null

type ItemsViewProps = {
  items: ItemInfo[]
  meta: ApiListMeta
  seq: number
  limit: number
  currentUser: CurrentUser | null
  errorMessage: string
  filters: ItemFilters
}

export default function ItemsView({
  items,
  meta,
  seq,
  limit,
  currentUser,
  errorMessage,
  filters,
}: ItemsViewProps) {
  const t = useT(itemsMessages)
  const statusFilterOptions = useStatusFilterOptions()
  const [dialog, setDialog] = useState<Dialog>(null)
  const [selectedItem, setSelectedItem] = useState<ItemInfo | null>(null)
  const [filterDialogOpen, setFilterDialogOpen] = useState(false)
  const { canCreateItem } = getItemCapabilities(currentUser?.permissions ?? [])
  const { isPending, submit } = useActionSubmit()

  function closeDialog() {
    setDialog(null)
    setSelectedItem(null)
  }

  function openFor(item: ItemInfo, nextDialog: Exclude<Dialog, "create" | null>) {
    setSelectedItem(item)
    setDialog(nextDialog)
  }

  // useListFeedback 統一處理「關窗 + 通知 + router.refresh()」，
  // 每個列表頁不必各自重寫一次成功後的收尾。
  const { notify, closeNotify, handleSuccess, handleError } = useListFeedback(closeDialog)

  function confirmDelete() {
    if (!selectedItem) return

    submit(() => deleteItem(selectedItem.id), {
      onSuccess: () => handleSuccess(t("itemDeleted")),
      onError: handleError,
      errorFallback: t("deleteFailed"),
    })
  }

  return (
    <Container size="lg" padded as="main">
      <ListPageHeader
        title={t("pageTitle")}
        subtitle={t("pageSubtitle")}
        showReset={meta.hasPrevious}
        onFilter={() => setFilterDialogOpen(true)}
        createAction={
          canCreateItem ? { label: t("create"), onClick: () => setDialog("create") } : undefined
        }
      />

      <ItemsTable
        items={items}
        meta={meta}
        seq={seq}
        limit={limit}
        currentUser={currentUser}
        errorMessage={errorMessage}
        onEdit={(item) => openFor(item, "edit")}
        onDelete={(item) => openFor(item, "delete")}
      />

      <FilterDialog
        key={filterDialogOpen ? "filter-open" : "filter-closed"}
        title={t("filterTitle")}
        open={filterDialogOpen}
        onClose={() => setFilterDialogOpen(false)}
        fields={[
          { name: "name", label: t("colName"), type: "text" },
          {
            name: "is_disabled",
            label: t("colStatus"),
            type: "select",
            options: statusFilterOptions,
          },
        ]}
        initialValues={{ name: filters.name, is_disabled: filters.isDisabled }}
      />

      <CreateItemDialog
        open={dialog === "create"}
        onClose={closeDialog}
        onSuccess={handleSuccess}
        onError={handleError}
      />
      {/* key 讓對話框在切換項目時重新掛載，state 才會吃到新的初始值 */}
      <EditItemDialog
        key={dialog === "edit" ? selectedItem?.id : "closed"}
        item={dialog === "edit" ? selectedItem : null}
        onClose={closeDialog}
        onSuccess={handleSuccess}
        onError={handleError}
      />
      <Confirm
        open={dialog === "delete"}
        title={t("deleteTitle")}
        message={t("deleteConfirm", { name: selectedItem?.name ?? "" })}
        confirmText={isPending ? t("deletePending") : t("delete")}
        onCancel={closeDialog}
        onClose={closeDialog}
        onConfirm={confirmDelete}
      />

      <Notify {...notify} onOpenChange={(open) => { if (!open) closeNotify() }} />
    </Container>
  )
}
