// **不要在這個檔案加上 "use server"** (同 shared/api/request.server.ts): 這是泛用的
// cookie 寫入原語, 成為 Server Action 後 client 就能任意寫入 access_token (session fixation)。
import "server-only"

import { cookies } from "next/headers"

import type { DataObject } from "@/shared/api/contract"

export async function createCookies(key: string, value: string, options: DataObject) {
  const cookieStore = await cookies()

  cookieStore.set(key, value, options)
}

export async function deleteCookies(key: string) {
  const cookieStore = await cookies()

  cookieStore.delete(key)
}
