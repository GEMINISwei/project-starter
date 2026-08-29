"use client"

import { useLocale, useT } from "@/shared/i18n/context"
import styles from "./roles.module.css"
import { rolesMessages } from "../i18n"
import { CATEGORY_LAYOUT, getPermissionActionLabel } from "../constants"
import type { PermissionOption, RolePermissionValue } from "../types"

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
  const locale = useLocale()
  const availableValues = new Set<RolePermissionValue>(permissionOptions.map((o) => o.value))

  function togglePermission(permission: string) {
    onChange(
      selectedPermissions.includes(permission)
        ? selectedPermissions.filter((item) => item !== permission)
        : [...selectedPermissions, permission],
    )
  }

  function renderItem(value: RolePermissionValue) {
    if (!availableValues.has(value)) return null
    const label = getPermissionActionLabel(value, locale)
    return (
      <label key={value} className={styles.permissionOption}>
        <input
          type="checkbox"
          checked={selectedPermissions.includes(value)}
          disabled={disabled}
          onChange={() => togglePermission(value)}
        />
        <span>{label}</span>
      </label>
    )
  }

  // 未被 CATEGORY_LAYOUT 涵蓋的權限放在「其他」分類
  const coveredValues = new Set<RolePermissionValue>(
    CATEGORY_LAYOUT.flatMap((c) => [...c.crud, ...c.extended]),
  )
  const uncategorized = permissionOptions.filter((o) => !coveredValues.has(o.value))

  return (
    <div>
      <div className={styles.permissionLabel}>{t("permissionsLabel")}</div>
      {error && <div className={styles.permissionError} role="alert">{error}</div>}
      {CATEGORY_LAYOUT.filter((category) => !category.hidden).map((category) => {
        const crudItems = category.crud.filter((v) => availableValues.has(v))
        const extendedItems = category.extended.filter((v) => availableValues.has(v))
        if (crudItems.length === 0 && extendedItems.length === 0) return null

        return (
          <div key={category.key} className={styles.permissionGroup}>
            <div className={styles.permissionGroupLabel}>{category.label[locale]}</div>
            {crudItems.length > 0 && (
              <div className={styles.permissionCrudRow}>
                {crudItems.map(renderItem)}
              </div>
            )}
            {extendedItems.length > 0 && (
              <div className={styles.permissionExtendedRow}>
                {extendedItems.map(renderItem)}
              </div>
            )}
          </div>
        )
      })}
      {uncategorized.length > 0 && (
        <div className={styles.permissionGroup}>
          <div className={styles.permissionGroupLabel}>{t("uncategorized")}</div>
          <div className={styles.permissionCrudRow}>
            {uncategorized.map((o) => renderItem(o.value))}
          </div>
        </div>
      )}
    </div>
  )
}
