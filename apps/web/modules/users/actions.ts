"use server"

import { apiPatch, apiPost } from "@/shared/api/request.server"
import {
  type ActionFormData,
  getActionFormString,
  getActionFormStrings,
} from "@/shared/api/action-form-data"
import type { ApiRequestBody } from "@/shared/api/contract"
import type { ResetPasswordFormValues } from "./types"

const refreshUsers = { path: "/users" }

export async function createUser(
  formData: ActionFormData<ApiRequestBody<"/users/", "post">>,
) {
  const roleIds = getActionFormStrings(formData, "role_ids")
  const data: ApiRequestBody<"/users/", "post"> = {
    username: getActionFormString(formData, "username"),
    nickname: getActionFormString(formData, "nickname"),
    password: getActionFormString(formData, "password"),
    role_ids: roleIds.length > 0 ? roleIds : undefined,
  }
  return apiPost({ url: "/users/", data, refresh: refreshUsers })
}

export async function updateUser(id: string, data: ApiRequestBody<"/users/{id}", "patch">) {
  return apiPatch({ url: "/users/{id}", params: { id }, data, refresh: refreshUsers })
}

export async function resetUserPassword(formData: ActionFormData<ResetPasswordFormValues>) {
  const id = getActionFormString(formData, "id")
  const password = getActionFormString(formData, "password")
  return apiPatch({ url: "/users/{id}/reset_password", params: { id }, data: { password } })
}
