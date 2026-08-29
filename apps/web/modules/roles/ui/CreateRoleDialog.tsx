"use client"

import { type FormEvent, useState } from "react"
import { FormDialog, TextInput, useActionSubmit } from "@/shared/ui"
import { useT } from "@/shared/i18n/context"
import { rolesMessages } from "../i18n"
import { createRole } from "../actions"

type CreateRoleDialogProps = {
  open: boolean
  onClose: () => void
  onSuccess: (message: string) => void
  onError: (message: string) => void
}

export default function CreateRoleDialog({
  open,
  onClose,
  onSuccess,
  onError,
}: CreateRoleDialogProps) {
  const t = useT(rolesMessages)
  const [name, setName] = useState("")
  const { isPending, submit, fieldError, clearFieldErrors } = useActionSubmit()

  function resetState() {
    setName("")
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

    submit(
      () => createRole({ name: name.trim() }),
      {
        onSuccess: () => {
          resetState()
          onSuccess(t("roleCreated"))
        },
        onError,
        errorFallback: t("createFailed"),
      }
    )
  }

  return (
    <FormDialog title={t("create")} open={open} isPending={isPending} submitText={t("createSubmit")} pendingText={t("createPending")} onClose={handleClose} onSubmit={submitCreate}>
      <TextInput label={t("colName")} value={name} error={fieldError("name")} required disabled={isPending} autoFocus onChange={setName} />
    </FormDialog>
  )
}
