"use client"

import { useRouter } from "next/navigation"
import { useState } from "react"
import { Button, Form, FormPageShell, Notify, useActionSubmit, useNotify } from "@/shared/ui"
import { useT } from "@/shared/i18n/context"
import { rolesMessages } from "../i18n"
import { getRoleDisplayName } from "../constants"
import { updateRole } from "../actions"
import type { PermissionOption, PermissionValue, RoleInfo, RolePermissionValue } from "../types"
import PermissionChecklist from "./PermissionChecklist"

type RoleEditViewProps = {
  role: RoleInfo
  permissionOptions: PermissionOption[]
}

export default function RoleEditView({ role, permissionOptions }: RoleEditViewProps) {
  const t = useT(rolesMessages)
  const router = useRouter()
  const [permissions, setPermissions] = useState<string[]>(
    role.permissions.filter(isPermissionValue),
  )
  const { isPending, submit, fieldError } = useActionSubmit()
  const { notify, notifyError, closeNotify } = useNotify()
  const readOnlyPermissions = role.permissions.includes("*")
    ? permissionOptions.map((o) => o.value)
    : role.permissions.filter(isPermissionValue)

  function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (permissions.length === 0) {
      notifyError(t("permissionRequired"))
      return
    }

    submit(
      () => updateRole(role.id, {
        name: role.name,
        permissions: permissions as RolePermissionValue[],
        is_disabled: role.is_disabled,
      }),
      {
        onSuccess: () => router.push("/roles"),
        onError: notifyError,
        errorFallback: t("updateFailed"),
      },
    )
  }

  return (
    <FormPageShell
      title={t("managePermissions")}
      subtitle={getRoleDisplayName(role, t)}
      backHref="/roles"
      backLabel={t("backToList")}
      actions={role.code ? null : (
        <Button
          type="submit"
          text={isPending ? t("saving") : t("save")}
          disabled={isPending}
          form="role-edit-form"
        />
      )}
    >
      {role.code ? (
        <PermissionChecklist
          permissionOptions={permissionOptions}
          selectedPermissions={readOnlyPermissions}
          disabled={true}
          onChange={() => {}}
        />
      ) : (
        <Form id="role-edit-form" onSubmit={handleSubmit}>
          <PermissionChecklist
            permissionOptions={permissionOptions}
            selectedPermissions={permissions}
            disabled={isPending}
            error={fieldError("permissions")}
            onChange={setPermissions}
          />

          <Notify {...notify} onOpenChange={(open) => { if (!open) closeNotify() }} />
        </Form>
      )}
    </FormPageShell>
  )
}

function isPermissionValue(permission: string): permission is PermissionValue {
  return permission !== "*"
}
