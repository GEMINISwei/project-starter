# 呼叫 API

前端的回應型別**由 `url` 推導**，不要自己指定：

```ts
const res = await apiGet({ url: "/roles/{id}", params: { id } })
if (res.status === "success") res.data.name   // 已窄化成 RoleInfo
else res.data.detail                          // 已窄化成錯誤形狀

// Server Action 的 payload 型別同樣從後端 schema 衍生
export async function updateRole(id: string, data: ApiRequestBody<"/roles/{id}", "patch">) {
  return apiPatch({ url: "/roles/{id}", params: { id }, data, refresh: refreshRoles })
}
```

- 路徑寫成**模板**（`/roles/{id}` + `params`），不是樣板字串 —— url 是字面值型別才推得出來。
  端點、方法、參數或 body 寫錯都會在 `tsc` 階段失敗。
- **收密碼或金鑰的 action 改收 `FormData`**（`shared/api/action-form-data.ts`）：Next 的開發
  log 會展開一般參數。
- **會寫 session cookie 的 action 回傳前要經過 `withoutAccessToken`**：Server Action 的回傳值會
  送進瀏覽器（`tests/token-cookie-writers.test.ts` 會擋）。
- 業務 entity 在模組的 `types.ts` 以 `Schema<"RoleInfo">`（`@/shared/api/contract`）命名，不手寫
  形狀，也不放進 shared；`@/shared/api/entities` 只有平台型別（`Permission`、`Language`、分頁形狀）。
- 需要目前登入者時用 `@/modules/auth/public.server` 的 `getCurrentUser()`；密碼規則在
  `@/modules/auth/public.client`。
