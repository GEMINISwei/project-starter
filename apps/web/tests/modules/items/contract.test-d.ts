/**
 * **範例模組**的型別契約測試 —— 示範「模組怎麼為自己的端點鎖住 wire contract」的寫法。
 *
 * 這**不是**每個模組的必備品，所以 users／roles 沒有對應檔案 —— 端點的形狀本來就由
 * `make gen-types` 產生的型別與 CI 的 drift job 保證，這裡是額外一層：把「哪些欄位是必填」
 * 這種容易在改 schema 時悄悄放寬的規則，寫成會編譯失敗的斷言。
 *
 * 值得為某個模組加一份的時機：該模組的 request body 有「少一個欄位也能通過」會造成
 * 實際損害的必填欄位。跟本專案其他型別測試一樣，靠 `tsc --noEmit` 執行，不會被 vitest 跑到
 *（理由見 `tests/shared/api/contract.test-d.ts`）。
 */

import { apiDelete, apiPatch, apiPost } from "@/shared/api/request.server"
import type { ApiRequestBody } from "@/shared/api/contract"

export async function itemContractStaysTyped() {
  // @ts-expect-error description 是既有 ItemCreate wire contract 的必填欄位
  await apiPost({ url: "/items/", data: { name: "x" } })

  const payload: ApiRequestBody<"/items/", "post"> = { name: "a", description: "b" }
  const created = await apiPost({ url: "/items/", data: payload })
  const patched = await apiPatch({
    url: "/items/{id}",
    params: { id: "1" },
    data: { name: "a", description: "b", is_disabled: false },
  })
  const removed = await apiDelete({ url: "/items/{id}", params: { id: "1" } })

  return { created, patched, removed }
}
