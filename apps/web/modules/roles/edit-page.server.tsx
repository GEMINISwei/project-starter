import "server-only"
import { redirect } from "next/navigation"
import { apiGet } from "@/shared/api/request.server"
import { getApiItemData, getApiListData } from "@/shared/api/response"
import { getT } from "@/shared/i18n/locale.server"
import { rolesMessages } from "./i18n"
import { canManageRole } from "./capabilities"
import { ROLES_PATH } from "./manifest"
import RoleEditView from "./ui/RoleEditView"

export type RoleEditPageProps = {
  params: Promise<{ id: string }>
}

export async function generateMetadata() {
  return { title: (await getT(rolesMessages))("managePermissions") }
}

export default async function RoleEditPage({ params }: RoleEditPageProps) {
  const { id } = await params
  const [roleRes, permissionsRes] = await Promise.all([
    apiGet({ url: "/roles/{id}", params: { id } }),
    apiGet({ url: "/roles/permission-options" }),
  ])

  const role = getApiItemData(roleRes)
  if (!role) redirect(ROLES_PATH)

  if (!canManageRole(role)) redirect(ROLES_PATH)

  const permissionOptions = getApiListData(permissionsRes)

  return (
    <RoleEditView role={role} permissionOptions={permissionOptions} />
  )
}
