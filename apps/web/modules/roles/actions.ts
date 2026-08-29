"use server"

import { apiPatch, apiPost } from "@/shared/api/request.server"
import type { ApiRequestBody } from "@/shared/api/contract"

const refreshRoles = { path: "/roles" }

export async function createRole(data: { name: string }) {
  return apiPost({
    // 建立時一律不帶權限，權限在編輯頁另外設定，所以這裡不直接用 request schema 當參數型別
    // —— 對外的介面刻意比後端窄。
    url: "/roles/",
    data: { name: data.name, permissions: [] },
    refresh: refreshRoles,
  })
}

export async function updateRole(id: string, data: ApiRequestBody<"/roles/{id}", "patch">) {
  return apiPatch({ url: "/roles/{id}", params: { id }, data, refresh: refreshRoles })
}
