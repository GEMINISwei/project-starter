"use client"

import { type FormEvent, useState } from "react"
import { FormDialog, SelectInput, TextInput, useActionSubmit, useActiveStatusOptions } from "@/shared/ui"
import { useT } from "@/shared/i18n/context"
import { itemsMessages } from "../i18n"
import { updateItem } from "../actions"
import type { ItemInfo } from "../types"

type EditItemDialogProps = {
  item: ItemInfo | null
  onClose: () => void
  onSuccess: (message: string) => void
  onError: (message: string) => void
}

export default function EditItemDialog({ item, onClose, onSuccess, onError }: EditItemDialogProps) {
  const t = useT(itemsMessages)
  const statusOptions = useActiveStatusOptions()
  const [name, setName] = useState(item?.name ?? "")
  const [description, setDescription] = useState(item?.description ?? "")
  const [isDisabled, setIsDisabled] = useState(item?.is_disabled ?? false)
  const { isPending, submit, fieldError } = useActionSubmit()

  function submitEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!item || !name.trim()) {
      onError(t("nameRequired"))
      return
    }

    submit(
      () => updateItem(item.id, {
        name: name.trim(),
        description: description.trim(),
        is_disabled: isDisabled,
      }),
      {
        // 完全沒改任何欄位時後端回 204，shared/api/request.server.ts 包成 status "info"，
        // useActionSubmit 也把它算成功 —— 對話框會正常關閉而不是跳錯誤。
        onSuccess: () => onSuccess(t("itemUpdated")),
        onError,
        errorFallback: t("updateFailed"),
      }
    )
  }

  return (
    <FormDialog title={t("editTitle")} open={item !== null} isPending={isPending} submitText={t("editSubmit")} pendingText={t("editPending")} onClose={onClose} onSubmit={submitEdit}>
      <TextInput label={t("colName")} value={name} error={fieldError("name")} required disabled={isPending} autoFocus onChange={setName} />
      <TextInput label={t("colDescription")} value={description} error={fieldError("description")} multiline disabled={isPending} onChange={setDescription} />
      <SelectInput
        label={t("colStatus")}
        value={isDisabled ? "disabled" : "active"}
        error={fieldError("is_disabled")}
        disabled={isPending}
        options={statusOptions}
        onChange={(value) => setIsDisabled(value === "disabled")}
      />
    </FormDialog>
  )
}
