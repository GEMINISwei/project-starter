"use server"

import { apiPost } from "@/shared/api/request.server"
import { type ActionFormData, getActionFormString } from "@/shared/api/action-form-data"
import { setAccessTokenCookie } from "@/shared/session/access-token.server"
import { withoutAccessToken } from "@/shared/session/token-response"
import type { LoginFormValues, SignupFormValues } from "./types"

export async function loginUser(formData: ActionFormData<LoginFormValues>) {
  const values: LoginFormValues = {
    username: getActionFormString(formData, "username"),
    password: getActionFormString(formData, "password"),
  }
  // 回應型別 (契約的 UserToken) 由 url 自動推導。
  const res = await apiPost({
    url: "/users/login",
    auth: "none",
    contentType: "form-data",
    data: values,
  })

  // cookie 的所有選項 (httpOnly、secure、sameSite、maxAge) 都在
  // `shared/session/access-token.server.ts`, 這裡不重複 —— 改密碼那條路徑也寫同一個
  // cookie, 兩邊各持一份設定的話, 飄掉的那一份不會有任何症狀。
  if (res.status === "success" && res.data.access_token) {
    await setAccessTokenCookie(res.data.access_token)
  }

  return withoutAccessToken(res)
}

export async function signupUser(formData: ActionFormData<SignupFormValues>) {
  const values: SignupFormValues = {
    nickname: getActionFormString(formData, "nickname"),
    username: getActionFormString(formData, "username"),
    password: getActionFormString(formData, "password"),
    register_key: getActionFormString(formData, "register_key"),
  }
  return apiPost({
    url: "/users/signup",
    auth: "none",
    data: values,
  })
}
