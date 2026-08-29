"use client"

import { KeyRound, Pencil } from "lucide-react"
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
import type { Translator } from "@/shared/i18n/dictionary"
import { rolesMessages } from "@/modules/roles/public.client"
import { usersMessages } from "../i18n"
import { formatRoleNames, getUserCapabilities } from "../capabilities"
import type { CurrentUser, RoleInfo, UserInfo } from "../types"

type UsersT = Translator<(typeof usersMessages)["zh"]>

type UserRowProps = {
  user: UserInfo
  roleNames: string
  isSelf: boolean
  canEdit: boolean
  canResetPassword: boolean
  t: UsersT
  onEdit: () => void
  onResetPassword: () => void
}

function UserRow({
  user,
  roleNames,
  isSelf,
  canEdit,
  canResetPassword,
  t,
  onEdit,
  onResetPassword,
}: UserRowProps) {
  return (
    <TableRow>
      <td data-label={t("colNickname")}>{user.nickname}{isSelf ? t("self") : ""}</td>
      <td data-label={t("colRole")}>{roleNames}</td>
      <td data-label={t("colStatus")}>
        <StatusBadge
          label={user.is_disabled ? t("statusDisabled") : t("statusActive")}
          variant={user.is_disabled ? "muted" : "success"}
        />
      </td>
      <td data-label={t("colActions")}>
        <ActionMenu
          items={[
            canEdit && { icon: <Pencil size={ICON_SIZE.sm} />, label: t("edit"), onClick: onEdit },
            canResetPassword && {
              icon: <KeyRound size={ICON_SIZE.sm} />,
              label: t("resetPassword"),
              onClick: onResetPassword,
            },
          ]}
        />
      </td>
    </TableRow>
  )
}

type UsersTableProps = {
  users: UserInfo[]
  roles: RoleInfo[]
  meta: ApiListMeta
  seq: number
  limit: number
  currentUser: CurrentUser | null
  errorMessage: string
  rolesErrorMessage: string
  onEdit: (user: UserInfo) => void
  onResetPassword: (user: UserInfo) => void
}

/**
 * 使用者列表本體（錯誤狀態、表格、分頁）。
 *
 * 字典與權限在這裡自己算，不由 `UsersView` 傳進來 —— 兩者都是 `currentUser` 的純推導，
 * 拉成 props 只會讓呼叫端多背五個變數，卻不會讓任何一邊更清楚。
 */
export default function UsersTable({
  users,
  roles,
  meta,
  seq,
  limit,
  currentUser,
  errorMessage,
  rolesErrorMessage,
  onEdit,
  onResetPassword,
}: UsersTableProps) {
  const t = useT(usersMessages)
  const roleT = useT(rolesMessages)
  const { isSuperUser, canCreateUser, canUpdateAnyUser, canUpdateOwnUser } = getUserCapabilities(
    currentUser?.permissions ?? [],
  )
  const currentUserId = currentUser?.id

  if (errorMessage) {
    return (
      <Surface>
        <ErrorState>{errorMessage}</ErrorState>
      </Surface>
    )
  }

  return (
    <>
      {rolesErrorMessage && canCreateUser && (
        <Surface>
          <ErrorState>{rolesErrorMessage}</ErrorState>
        </Surface>
      )}
      <ListTableCard
        headers={[t("colNickname"), t("colRole"), t("colStatus"), t("colActions")]}
        isEmpty={users.length === 0}
        emptyText={t("empty")}
      >
        {users.map((user) => {
          const isSelf = user.id === currentUserId

          return (
            <UserRow
              key={user.id}
              user={user}
              roleNames={formatRoleNames(user, roles, t, roleT)}
              isSelf={isSelf}
              canEdit={canUpdateAnyUser || (isSelf && canUpdateOwnUser)}
              canResetPassword={isSuperUser}
              t={t}
              onEdit={() => onEdit(user)}
              onResetPassword={() => onResetPassword(user)}
            />
          )
        })}
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
