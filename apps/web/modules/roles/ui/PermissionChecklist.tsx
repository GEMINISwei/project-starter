"use client"

import { useT } from "@/shared/i18n/context"
import styles from "./roles.module.css"
import { rolesMessages } from "../i18n"
import { groupPermissionOptions } from "../capabilities"
import type { PermissionOption } from "../types"

interface PermissionChecklistProps {
  permissionOptions: PermissionOption[]
  selectedPermissions: string[]
  onChange: (permissions: string[]) => void
  disabled?: boolean
  error?: string
}

export default function PermissionChecklist({
  permissionOptions,
  selectedPermissions,
  onChange,
  disabled = false,
  error,
}: PermissionChecklistProps) {
  const t = useT(rolesMessages)

  function togglePermission(permission: string) {
    onChange(
      selectedPermissions.includes(permission)
        ? selectedPermissions.filter((item) => item !== permission)
        : [...selectedPermissions, permission],
    )
  }

  return (
    <div>
      <div className={styles.permissionLabel}>{t("permissionsLabel")}</div>
      {error && <div className={styles.permissionError} role="alert">{error}</div>}
      {permissionOptions.length === 0 && (
        <div className={styles.permissionEmpty}>{t("noPermissionOptions")}</div>
      )}
      {groupPermissionOptions(permissionOptions).map((group) => (
        <div key={group.category} className={styles.permissionGroup}>
          <div className={styles.permissionGroupLabel}>{group.category}</div>
          <div className={styles.permissionRow}>
            {group.options.map((option) => (
              <label key={option.value} className={styles.permissionOption}>
                <input
                  type="checkbox"
                  checked={selectedPermissions.includes(option.value)}
                  disabled={disabled}
                  onChange={() => togglePermission(option.value)}
                />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
