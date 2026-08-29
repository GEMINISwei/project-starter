"use client"

import { type FormEvent, useState } from "react"
import { FormDialog, SelectInput, TextInput, useActionSubmit, useActiveStatusOptions } from "@/shared/ui"
import { useT } from "@/shared/i18n/context"
import { usersMessages } from "../i18n"
import { updateUser } from "../actions"
import type { CurrentUser, UserInfo } from "../types"

type EditUserDialogProps = {
  user: UserInfo | null
  onClose: () => void
  onSuccess: (message: string) => void
  onError: (message: string) => void
  currentUser: CurrentUser | null
  canUpdateAnyUser: boolean
  canDeleteUser: boolean
  isSuperAdminUser: (user: UserInfo) => boolean
  roleOptions: Array<{ value: string; label: string }>
}

/**
 * 禁止自我提權或停用自己；超級管理者帳號也不可停用。
 *
 * 抽成具名函式而不是寫在 JSX 的 `&&` 鏈裡：那兩條鏈各有四個條件，混在畫面裡讀不出意圖，
 * 也會讓元件的分支數翻倍。
 */
function getEditableFields({
  user,
  currentUser,
  canUpdateAnyUser,
  canDeleteUser,
  isSuperAdminUser,
  hasRoleOptions,
}: {
  user: UserInfo | null
  currentUser: CurrentUser | null
  canUpdateAnyUser: boolean
  canDeleteUser: boolean
  isSuperAdminUser: (user: UserInfo) => boolean
  hasRoleOptions: boolean
}) {
  if (!user) return { canAssignRole: false, canToggleStatus: false }

  const isSelf = user.id === currentUser?.id

  return {
    canAssignRole: canUpdateAnyUser && !isSelf && hasRoleOptions,
    canToggleStatus: canDeleteUser && !isSelf && !isSuperAdminUser(user),
  }
}

export default function EditUserDialog({
  user,
  onClose,
  onSuccess,
  onError,
  currentUser,
  canUpdateAnyUser,
  canDeleteUser,
  isSuperAdminUser,
  roleOptions,
}: EditUserDialogProps) {
  const t = useT(usersMessages)
  const statusOptions = useActiveStatusOptions()
  const [nickname, setNickname] = useState(user?.nickname ?? "")
  const [isDisabled, setIsDisabled] = useState(user?.is_disabled ?? false)
  const [selectedRoleId, setSelectedRoleId] = useState(user?.role_ids[0] ?? "")
  const { isPending, submit, fieldError } = useActionSubmit()
  const { canAssignRole, canToggleStatus } = getEditableFields({
    user,
    currentUser,
    canUpdateAnyUser,
    canDeleteUser,
    isSuperAdminUser,
    hasRoleOptions: roleOptions.length > 0,
  })

  function submitEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!user || !nickname.trim()) {
      onError(t("nicknameRequired"))
      return
    }

    const canUpdateRole = canUpdateAnyUser && user.id !== currentUser?.id
    submit(
      () => updateUser(user.id, {
        nickname: nickname.trim(),
        is_disabled: isDisabled,
        role_ids: canUpdateRole && selectedRoleId ? [selectedRoleId] : undefined,
      }),
      {
        onSuccess: () => onSuccess(t("userUpdated")),
        onError,
        errorFallback: t("updateFailed"),
      }
    )
  }

  return (
    <FormDialog
      title={t("editTitle")}
      open={user !== null}
      isPending={isPending}
      submitText={t("editSubmit")}
      pendingText={t("editPending")}
      onClose={onClose}
      onSubmit={submitEdit}
    >
      <TextInput label={t("colUsername")} value={user?.username ?? ""} disabled />
      <TextInput
        label={t("colNickname")}
        value={nickname}
        error={fieldError("nickname")}
        required
        disabled={isPending}
        autoFocus
        onChange={setNickname}
      />
      {canAssignRole && (
        <SelectInput
          label={t("colRole")}
          value={selectedRoleId}
          error={fieldError("role_ids")}
          disabled={isPending}
          options={[{ value: "", label: t("roleUnassigned") }, ...roleOptions]}
          onChange={setSelectedRoleId}
        />
      )}
      {canToggleStatus && (
        <SelectInput
          label={t("colStatus")}
          value={isDisabled ? "disabled" : "active"}
          error={fieldError("is_disabled")}
          disabled={isPending}
          options={statusOptions}
          onChange={(value) => setIsDisabled(value === "disabled")}
        />
      )}
    </FormDialog>
  )
}
