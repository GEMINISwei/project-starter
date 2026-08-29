// **不要在這個檔案加上 "use server"**（同 shared/api/request.server.ts）：這是泛用的
// cookie 讀寫原語，成為 Server Action 後 client 就能任意寫入 access_token（session fixation）。
import "server-only"

import { cookies } from "next/headers"

import type { DataObject } from "@/shared/api/contract"

export async function createCookies(key: string, value: string, options: DataObject) {
  const cookieStore = await cookies()

  cookieStore.set(key, value, options)
}

/**
 * @knipignore repo 內目前沒有呼叫端，但 create／get／delete 這組原語刻意成套提供 ——
 * 少了讀取的那一半，下游要讀 cookie 時會自己再寫一個（於是 `httpOnly` 之類的設定
 * 就有兩份各自飄的來源）。同檔的另外兩個 export 有人用，不在豁免範圍。
 */
export async function getCookies(key: string): Promise<string | undefined> {
  const cookieStore = await cookies()

  return cookieStore.get(key)?.value
}

export async function deleteCookies(key: string) {
  const cookieStore = await cookies()

  cookieStore.delete(key)
}
