"use server"

import { type ActionFormData, getActionFormString } from "@/shared/api/action-form-data"
import { apiPatch } from "@/shared/api/request.server"
import { setAccessTokenCookie } from "@/shared/session/access-token.server"
import { withoutAccessToken } from "@/shared/session/token-response"
import type { PasswordChangeRequest, ProfileUpdateRequest } from "./types"

export async function changeOwnPassword(formData: ActionFormData<PasswordChangeRequest>) {
  const res = await apiPatch({
    url: "/users/me/password",
    data: {
      current_password: getActionFormString(formData, "current_password"),
      new_password: getActionFormString(formData, "new_password"),
    },
  })

  // **這一段不是可選的。** 後端換密碼時把 `auth_version` +1, 撤銷了這個人所有既有的
  // session —— 包含發出這次請求的那一張。不覆寫 cookie 的話, 使用者的下一個動作會拿到
  // 401 被導回登入頁, 而畫面上剛剛才說更新成功。
  if (res.status === "success" && res.data.access_token) {
    await setAccessTokenCookie(res.data.access_token)
  }

  return withoutAccessToken(res)
}

export async function updateOwnProfile(formData: ActionFormData<ProfileUpdateRequest>) {
  return apiPatch({
    url: "/users/me",
    data: { nickname: getActionFormString(formData, "nickname") },
  })
}
