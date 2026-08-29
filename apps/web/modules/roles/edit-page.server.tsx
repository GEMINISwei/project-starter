import { redirect } from "next/navigation"
import { apiGet } from "@/shared/api/request.server"
import { getApiItemData, getApiListData } from "@/shared/api/response"
import { getCurrentUser } from "@/shared/session/current-user.server"
import { getT } from "@/shared/i18n/locale.server"
import { rolesMessages } from "./i18n"
import { getRoleCapabilities } from "./capabilities"
import RoleEditView from "./ui/RoleEditView"

export type RoleEditPageProps = {
  params: Promise<{ id: string }>
}

export async function generateMetadata() {
  return { title: (await getT(rolesMessages))("managePermissions") }
}

export default async function RoleEditPage({ params }: RoleEditPageProps) {
  const { id } = await params
  // getCurrentUser() 有 React `cache()`，同一次 render 內與 layout 共用同一筆結果。
  const [roleRes, permissionsRes, { data: currentUser }] = await Promise.all([
    apiGet({ url: "/roles/{id}", params: { id } }),
    apiGet({ url: "/permissions/" }),
    getCurrentUser(),
  ])

  const role = getApiItemData(roleRes)
  if (!role) redirect("/roles")
  if (role.code !== null) redirect("/roles")

  if (!getRoleCapabilities(currentUser?.permissions ?? []).canUpdateRole) redirect("/roles")

  const permissionOptions = getApiListData(permissionsRes)

  return (
    <RoleEditView
      role={role}
      permissionOptions={permissionOptions}
    />
  )
}
