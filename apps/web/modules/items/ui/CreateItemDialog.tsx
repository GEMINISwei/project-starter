"use client"

import { type FormEvent, useState } from "react"
import { FormDialog, TextInput, useActionSubmit } from "@/shared/ui"
import { useT } from "@/shared/i18n/context"
import { itemsMessages } from "../i18n"
import { createItem } from "../actions"

// 慣例：每個 create/edit 對話框各自獨立成一個元件檔，不要內嵌在 View 裡。

type CreateItemDialogProps = {
  open: boolean
  onClose: () => void
  onSuccess: (message: string) => void
  onError: (message: string) => void
}

export default function CreateItemDialog({
  open,
  onClose,
  onSuccess,
  onError,
}: CreateItemDialogProps) {
  const t = useT(itemsMessages)
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  // useActionSubmit 包掉 useTransition 與成功/失敗分支，不要自己接一次。
  const { isPending, submit, fieldError, clearFieldErrors } = useActionSubmit()

  function resetState() {
    setName("")
    setDescription("")
    clearFieldErrors()
  }

  function handleClose() {
    resetState()
    onClose()
  }

  function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!name.trim()) {
      onError(t("nameRequired"))
      return
    }

    submit(() => createItem({ name: name.trim(), description: description.trim() }), {
      onSuccess: () => {
        resetState()
        onSuccess(t("itemCreated"))
      },
      onError,
      errorFallback: t("createFailed"),
    })
  }

  return (
    <FormDialog title={t("create")} open={open} isPending={isPending} submitText={t("createSubmit")} pendingText={t("createPending")} onClose={handleClose} onSubmit={submitCreate}>
      <TextInput label={t("colName")} value={name} error={fieldError("name")} required disabled={isPending} autoFocus onChange={setName} />
      <TextInput label={t("colDescription")} value={description} error={fieldError("description")} multiline disabled={isPending} onChange={setDescription} />
    </FormDialog>
  )
}
