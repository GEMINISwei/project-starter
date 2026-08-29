"use client"

import { useState } from "react"
import { Container, ListPageHeader, Notify, useListFeedback } from "@/shared/ui"
import { hasAllPermission } from "@/shared/access/permissions"
import type { ApiListMeta } from "@/shared/api/response"
import { useT } from "@/shared/i18n/context"
// 角色顯示名稱的規則（系統角色走字典）由 roles 模組唯一擁有，這裡經 public entry 取用。
import { getRoleDisplayName, rolesMessages } from "@/modules/roles/public.client"
import { usersMessages } from "../i18n"
import { getUserCapabilities, isSuperAdminUser } from "../capabilities"
import type { CurrentUser, RoleInfo, UserFilters, UserInfo } from "../types"
import CreateUserDialog from "./CreateUserDialog"
import EditUserDialog from "./EditUserDialog"
import ResetPasswordDialog from "./ResetPasswordDialog"
import UsersTable from "./UsersTable"
import UsersFilterDialog from "./UsersFilterDialog"

type Dialog = "create" | "edit" | "reset" | null

type UsersViewProps = {
  users: UserInfo[]
  meta: ApiListMeta
  seq: number
  limit: number
  currentUser: CurrentUser | null
  roles: RoleInfo[]
  errorMessage: string
  rolesErrorMessage: string
  filters: UserFilters
}

export default function UsersView({
  users,
  meta,
  seq,
  limit,
  currentUser,
  roles,
  errorMessage,
  rolesErrorMessage,
  filters,
}: UsersViewProps) {
  const t = useT(usersMessages)
  const roleT = useT(rolesMessages)
  const showReset = meta.hasPrevious
  const [dialog, setDialog] = useState<Dialog>(null)
  const [selectedUser, setSelectedUser] = useState<UserInfo | null>(null)
  const [filterDialogOpen, setFilterDialogOpen] = useState(false)
  const { canCreateUser, canUpdateAnyUser, canDeleteUser } = getUserCapabilities(
    currentUser?.permissions ?? [],
  )
  const enabledRoles = roles.filter(
    (role) => !role.is_disabled && !hasAllPermission(role.permissions),
  )
  // 只有「可以指派給人」的角色進得了這份清單；篩選用的那份規則不同，
  // 由 UsersFilterDialog 自己組。
  const roleOptions = enabledRoles.map((role) => ({
    value: role.id,
    label: getRoleDisplayName(role, roleT),
  }))

  function closeSelectedDialog() {
    setDialog(null)
    setSelectedUser(null)
  }

  function openCreate() { setDialog("create") }

  function openFor(user: UserInfo, nextDialog: Exclude<Dialog, "create" | null>) {
    setSelectedUser(user)
    setDialog(nextDialog)
  }

  const { notify, closeNotify, handleSuccess, handleError } = useListFeedback(closeSelectedDialog)

  return (
    <Container size="lg" padded as="main">
      <ListPageHeader
        title={t("heading")}
        subtitle={t("subtitle")}
        showReset={showReset}
        onFilter={() => setFilterDialogOpen(true)}
        createAction={canCreateUser ? { label: t("create"), onClick: openCreate } : undefined}
      />

      <UsersTable
        users={users}
        roles={roles}
        meta={meta}
        seq={seq}
        limit={limit}
        currentUser={currentUser}
        errorMessage={errorMessage}
        rolesErrorMessage={rolesErrorMessage}
        onEdit={(user) => openFor(user, "edit")}
        onResetPassword={(user) => openFor(user, "reset")}
      />

      <CreateUserDialog
        open={dialog === "create"}
        onClose={() => setDialog(null)}
        onSuccess={handleSuccess}
        onError={handleError}
        canUpdateAnyUser={canUpdateAnyUser}
        roleOptions={roleOptions}
      />
      <EditUserDialog
        key={dialog === "edit" ? selectedUser?.id : "closed"}
        user={dialog === "edit" ? selectedUser : null}
        onClose={closeSelectedDialog}
        onSuccess={handleSuccess}
        onError={handleError}
        currentUser={currentUser}
        canUpdateAnyUser={canUpdateAnyUser}
        canDeleteUser={canDeleteUser}
        isSuperAdminUser={(user) => isSuperAdminUser(user, roles)}
        roleOptions={roleOptions}
      />
      <ResetPasswordDialog
        user={dialog === "reset" ? selectedUser : null}
        onClose={closeSelectedDialog}
        onSuccess={handleSuccess}
        onError={handleError}
      />
      <UsersFilterDialog
        key={filterDialogOpen ? "filter-open" : "filter-closed"}
        open={filterDialogOpen}
        onClose={() => setFilterDialogOpen(false)}
        roles={roles}
        filters={filters}
      />

      <Notify {...notify} onOpenChange={(open) => { if (!open) closeNotify() }} />
    </Container>
  )
}
