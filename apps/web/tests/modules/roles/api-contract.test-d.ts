/**
 * API 型別契約的守門測試 —— **這個檔案不會被執行**, 它靠 `tsc --noEmit` 檢查。
 *
 * 這裡用 `@ts-expect-error` 而不是 vitest 的 `expectTypeOf`: `request.server.ts` 帶
 * `import "server-only"`, 在 vitest 環境載入會直接拋錯, 沒辦法出現在會被執行的測試裡。
 * `@ts-expect-error` 是編譯期語意, 而且是**雙向**的:
 *
 * - 該報錯的用法沒報錯 → `@ts-expect-error` 變成「未使用」, tsc 會報錯
 * - 不該報錯的用法報錯了 → 直接就是編譯錯誤
 *
 * 契約被放寬或被弄壞, 兩種情況都會讓 CI 紅燈。
 *
 * 守的是 `shared/api` 的型別機制, 但題材只能是**這個專案真的有的**端點 (`apiGet` 等直接綁
 * 產生出來的 `paths`), 所以放在擁有那些端點的 roles 底下, 而不是 `tests/shared/`。
 * 拿掉 roles 時把題材換成留下來的模組的端點。
 */

import { apiDelete, apiGet, apiPatch, apiPost } from "@/shared/api/request.server"
import type { ApiRequestBody } from "@/shared/api/contract"

export async function rejectsUnknownPath() {
  // @ts-expect-error 端點不存在 (tsc 甚至會提示 "Did you mean '/roles/'?")
  await apiGet({ url: "/rolez/" })
}

export async function rejectsWrongMethodForPath() {
  // @ts-expect-error /users/me 沒有 POST (只有 GET 與 PATCH)
  await apiPost({ url: "/users/me", data: {} })
}

export async function rejectsMissingPathParams() {
  // @ts-expect-error /roles/{id} 需要 params: { id }
  await apiGet({ url: "/roles/{id}" })
}

export async function rejectsIncompleteBody() {
  // @ts-expect-error 少了必填的 permissions
  await apiPost({ url: "/roles/", data: { name: "x" } })
}

export async function rejectsUnknownBodyField() {
  // @ts-expect-error bogus 不在 RoleCreate 裡
  await apiPost({ url: "/roles/", data: { name: "x", permissions: [], bogus: 1 } })
}

// 這裡原本還有一條 `rejectsBodyOnBodilessEndpoint`, 守 `BodyField` 對「沒有 body 的
// POST/PATCH」的處理 (見 shared/api/contract.ts 的 `RequestBody`)。**目前的端點集合裡
// 一條都沒有**, 所以那條測試沒有題材可寫, 只能連同它守的保護一起先放著 ——
// 新增這種端點時 (`POST /xxx/action` 這類「動詞端點」很常見) 請把它加回來:
//
//     // @ts-expect-error POST /xxx/action 沒有 request body
//     await apiPost({ url: "/xxx/action", data: { anything: 1 } })
//     const ok = await apiPost({ url: "/xxx/action" })   // 不必傳 data

export async function rejectsReadingResponseAsWrongEntity() {
  const res = await apiGet({ url: "/roles/{id}", params: { id: "1" } })
  if (res.status === "success") {
    // @ts-expect-error 這是角色, 不是使用者
    return res.data.username
  }
}

// --- 正確用法必須維持可編譯 (放寬契約以外的另一個方向) ---------------------

export async function acceptsValidCalls() {
  const role = await apiGet({ url: "/roles/{id}", params: { id: "1" } })
  const list = await apiGet({ url: "/roles/permission-options" })
  const created = await apiPost({ url: "/roles/", data: { name: "a", permissions: [] } })
  const patched = await apiPatch({
    url: "/roles/{id}",
    params: { id: "1" },
    data: { name: "a", permissions: [], is_disabled: false },
  })
  const removed = await apiDelete({ url: "/roles/{id}", params: { id: "1" } })

  return { role, list, created, patched, removed }
}

// Server Action 的 payload 型別確實衍生自後端 schema。
export function bodyTypeIsDerivedFromSchema() {
  const payload: ApiRequestBody<"/roles/", "post"> = { name: "a", permissions: [] }
  // @ts-expect-error 型別是從後端 schema 來的, 不是任意物件
  const wrong: ApiRequestBody<"/roles/", "post"> = { name: "a" }

  return [payload, wrong]
}
