"use server"

import { apiDelete, apiPatch, apiPost } from "@/shared/api/request.server"
import type { ApiRequestBody } from "@/shared/api/contract"

// 寫入一律走具名的 Server Action，不把 `shared/api/request.server.ts` 直接暴露成
// Server Action —— 否則任何 client component 都能拿使用者的 cookie 打任意端點
//（理由見 `shared/api/request.server.ts` 開頭的說明）。
//
// payload 型別由後端的 request schema 衍生，確保必填欄位的變更能在編譯期被捕捉。

const refreshItems = { path: "/items" }

export async function createItem(data: ApiRequestBody<"/items/", "post">) {
  return apiPost({ url: "/items/", data, refresh: refreshItems })
}

export async function updateItem(id: string, data: ApiRequestBody<"/items/{id}", "patch">) {
  return apiPatch({ url: "/items/{id}", params: { id }, data, refresh: refreshItems })
}

export async function deleteItem(id: string) {
  return apiDelete({ url: "/items/{id}", params: { id }, refresh: refreshItems })
}
