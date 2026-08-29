"use client"

import { type FormEvent, useState } from "react"
import { FormDialog, SelectInput, TextInput, useActionSubmit } from "@/shared/ui"
import { useLocale, useT } from "@/shared/i18n/context"
import { validateNewPassword } from "@/shared/session/password-policy"
import { createActionFormData } from "@/shared/api/action-form-data"
import { usersMessages } from "../i18n"
import { createUser } from "../actions"

type CreateUserDialogProps = {
  open: boolean
  onClose: () => void
  onSuccess: (message: string) => void
  onError: (message: string) => void
  canUpdateAnyUser: boolean
  roleOptions: Array<{ value: string; label: string }>
}

export default function CreateUserDialog({
  open,
  onClose,
  onSuccess,
  onError,
  canUpdateAnyUser,
  roleOptions,
}: CreateUserDialogProps) {
  const t = useT(usersMessages)
  const locale = useLocale()
  const [username, setUsername] = useState("")
  const [nickname, setNickname] = useState("")
  const [password, setPassword] = useState("")
  const [selectedRoleId, setSelectedRoleId] = useState("")
  const { isPending, submit, fieldError, clearFieldErrors } = useActionSubmit()

  function resetState() {
    setUsername("")
    setNickname("")
    setPassword("")
    setSelectedRoleId("")
    clearFieldErrors()
  }

  function handleClose() {
    resetState()
    onClose()
  }

  function submitCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const passwordError = validateNewPassword(password, locale)
    if (!username.trim() || !nickname.trim() || passwordError) {
      onError(passwordError ?? t("usernameNicknameRequired"))
      return
    }

    submit(
      () => createUser(createActionFormData({
        username: username.trim(),
        nickname: nickname.trim(),
        password,
        role_ids: selectedRoleId ? [selectedRoleId] : undefined,
      })),
      {
        onSuccess: () => {
          resetState()
          onSuccess(t("userCreated"))
        },
        onError,
        errorFallback: t("createFailed"),
      }
    )
  }

  return (
    <FormDialog title={t("create")} open={open} isPending={isPending} submitText={t("createSubmit")} pendingText={t("createPending")} onClose={handleClose} onSubmit={submitCreate}>
      <TextInput label={t("colNickname")} value={nickname} error={fieldError("nickname")} required disabled={isPending} autoFocus onChange={setNickname} />
      <TextInput label={t("colUsername")} value={username} error={fieldError("username")} required disabled={isPending} onChange={setUsername} />
      <TextInput label={t("password")} type="password" value={password} error={fieldError("password")} required disabled={isPending} onChange={setPassword} />
      {canUpdateAnyUser && roleOptions.length > 0 && (
        <SelectInput
          label={t("colRole")}
          value={selectedRoleId}
          error={fieldError("role_ids")}
          disabled={isPending}
          options={[{ value: "", label: t("roleUnassigned") }, ...roleOptions]}
          onChange={setSelectedRoleId}
        />
      )}
    </FormDialog>
  )
}
