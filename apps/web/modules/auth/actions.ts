"use server"

import { headers } from "next/headers"

import { apiPost } from "@/shared/api/request.server"
import { type ActionFormData, getActionFormString } from "@/shared/api/action-form-data"
import { resolveCookieSecure } from "@/shared/session/cookie-options"
import { createCookies } from "@/shared/session/cookies.server"
import type { LoginFormValues, SignupFormValues } from "./types"

// EXPIRE_HOURS 沒設或格式錯誤時，Number() 會得到 NaN，maxAge: NaN 會讓 cookie 變成
// session cookie（關掉瀏覽器就登出）而且沒有任何警告。這裡明確給一個保守的預設值。
const DEFAULT_EXPIRE_HOURS = 1

function getCookieMaxAgeSeconds() {
  const hours = Number(process.env.EXPIRE_HOURS)

  return 60 * 60 * (Number.isFinite(hours) && hours > 0 ? hours : DEFAULT_EXPIRE_HOURS)
}

export async function loginUser(formData: ActionFormData<LoginFormValues>) {
  const values: LoginFormValues = {
    username: getActionFormString(formData, "username"),
    password: getActionFormString(formData, "password"),
  }
  // 回應型別（AuthToken）由 url 自動推導。
  const res = await apiPost({
    url: "/users/login",
    auth: "none",
    contentType: "form-data",
    data: values,
  })

  if (res.status === "success" && res.data.access_token) {
    const headerStore = await headers()

    await createCookies("access_token", res.data.access_token, {
      httpOnly: true,
      // 依這次請求實際走的協定決定，而不是依 NODE_ENV —— 理由見 resolveCookieSecure。
      secure: resolveCookieSecure(headerStore.get("x-forwarded-proto")),
      // sameSite: "lax" 是目前的 CSRF 防線：跨站發起的 POST/PATCH/DELETE 不會帶上這個
      // cookie。因此所有會改變狀態的操作都**必須**用非 GET 方法（本專案的 Server Action
      // 都是 POST，符合這個前提）。若日後新增以 GET 觸發的變更操作，這道防線就會失效。
      sameSite: "lax",
      path: "/",
      maxAge: getCookieMaxAgeSeconds(),
    })
  }

  return res
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
