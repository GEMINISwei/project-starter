"use client"

import { useState } from "react"
import {
  Container,
  FilterDialog,
  ListPageHeader,
  Notify,
  useListFeedback,
  useStatusFilterOptions,
} from "@/shared/ui"
import type { ApiListMeta } from "@/shared/api/response"
import { useT } from "@/shared/i18n/context"
import { rolesMessages } from "../i18n"
import { getRoleCapabilities } from "../capabilities"
import type { CurrentUser, RoleFilters, RoleInfo } from "../types"
import CreateRoleDialog from "./CreateRoleDialog"
import EditRoleDialog from "./EditRoleDialog"
import RolesTable from "./RolesTable"

type Dialog = "create" | "edit" | null

type RolesViewProps = {
  roles: RoleInfo[]
  meta: ApiListMeta
  seq: number
  limit: number
  currentUser: CurrentUser | null
  errorMessage: string
  filters: RoleFilters
}

export default function RolesView({
  roles,
  meta,
  seq,
  limit,
  currentUser,
  errorMessage,
  filters,
}: RolesViewProps) {
  const t = useT(rolesMessages)
  const statusFilterOptions = useStatusFilterOptions()
  const showReset = meta.hasPrevious
  const [dialog, setDialog] = useState<Dialog>(null)
  const [selectedRole, setSelectedRole] = useState<RoleInfo | null>(null)
  const [filterDialogOpen, setFilterDialogOpen] = useState(false)
  const { canCreateRole } = getRoleCapabilities(currentUser?.permissions ?? [])

  function closeDialog() {
    setDialog(null)
    setSelectedRole(null)
  }

  function openCreate() {
    setDialog("create")
  }

  function openEdit(role: RoleInfo) {
    setSelectedRole(role)
    setDialog("edit")
  }

  const { notify, closeNotify, handleSuccess, handleError } = useListFeedback(closeDialog)

  return (
    <Container size="lg" padded as="main">
      <ListPageHeader
        title={t("heading")}
        subtitle={t("subtitle")}
        showReset={showReset}
        onFilter={() => setFilterDialogOpen(true)}
        createAction={canCreateRole ? { label: t("create"), onClick: openCreate } : undefined}
      />

      <RolesTable
        roles={roles}
        meta={meta}
        seq={seq}
        limit={limit}
        currentUser={currentUser}
        errorMessage={errorMessage}
        onEdit={openEdit}
      />

      <FilterDialog
        key={filterDialogOpen ? "filter-open" : "filter-closed"}
        title={t("filterTitle")}
        open={filterDialogOpen}
        onClose={() => setFilterDialogOpen(false)}
        fields={[
          { name: "name", label: t("colName"), type: "text" },
          {
            name: "is_disabled",
            label: t("colStatus"),
            type: "select",
            options: statusFilterOptions,
          },
        ]}
        initialValues={{ name: filters.name, is_disabled: filters.isDisabled }}
      />

      <CreateRoleDialog
        open={dialog === "create"}
        onClose={closeDialog}
        onSuccess={handleSuccess}
        onError={handleError}
      />
      <EditRoleDialog
        key={dialog === "edit" ? selectedRole?.id : "closed"}
        role={dialog === "edit" ? selectedRole : null}
        onClose={closeDialog}
        onSuccess={handleSuccess}
        onError={handleError}
      />

      <Notify {...notify} onOpenChange={(open) => { if (!open) closeNotify() }} />
    </Container>
  )
}
