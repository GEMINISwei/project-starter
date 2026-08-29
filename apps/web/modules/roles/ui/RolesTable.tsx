"use client"

import { useRouter } from "next/navigation"
import { Pencil, ShieldCheck } from "lucide-react"
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
import { rolesMessages } from "../i18n"
import { getRoleDisplayName } from "../constants"
import { getRoleCapabilities } from "../capabilities"
import type { CurrentUser, RoleInfo } from "../types"

type RolesTableProps = {
  roles: RoleInfo[]
  meta: ApiListMeta
  seq: number
  limit: number
  currentUser: CurrentUser | null
  errorMessage: string
  onEdit: (role: RoleInfo) => void
}

/**
 * 角色列表本體（錯誤狀態、表格、分頁）。
 *
 * 字典與權限在這裡自己算，不由 `RolesView` 傳進來 —— 兩者都是 `currentUser` 的純推導。
 */
export default function RolesTable({
  roles,
  meta,
  seq,
  limit,
  currentUser,
  errorMessage,
  onEdit,
}: RolesTableProps) {
  const t = useT(rolesMessages)
  const router = useRouter()
  const { canUpdateRole } = getRoleCapabilities(currentUser?.permissions ?? [])

  function getPermissionText(role: RoleInfo) {
    if (role.permissions.includes("*")) return t("allPermissions")
    return t("permissionCount", { count: role.permissions.length })
  }

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
        headers={[t("colName"), t("colPermissions"), t("colStatus"), t("colActions")]}
        isEmpty={roles.length === 0}
        emptyText={t("empty")}
      >
        {roles.map((role) => (
          <TableRow key={role.id}>
            <td data-label={t("colName")}>{getRoleDisplayName(role, t)}</td>
            <td data-label={t("colPermissions")}>{getPermissionText(role)}</td>
            <td data-label={t("colStatus")}>
              <StatusBadge
                label={role.is_disabled ? t("statusDisabled") : t("statusActive")}
                variant={role.is_disabled ? "muted" : "success"}
              />
            </td>
            <td data-label={t("colActions")}>
              <ActionMenu
                items={[
                  canUpdateRole && {
                    icon: <Pencil size={ICON_SIZE.sm} />,
                    label: t("edit"),
                    onClick: () => onEdit(role),
                  },
                  // 只有自訂角色能改權限：系統角色的權限是模板的一部分，
                  // 改了會在下次同步時被蓋掉。
                  canUpdateRole &&
                    role.code === null && {
                      icon: <ShieldCheck size={ICON_SIZE.sm} />,
                      label: t("managePermissions"),
                      onClick: () => router.push(`/roles/${role.id}/edit`),
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
