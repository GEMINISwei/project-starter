// 平台層級的 entity 型別: 權限、語系與列表回應形狀。一律從 `generated/schema.d.ts` 衍生
// (後端 OpenAPI 產生的, `make gen-types`)。不要在這裡手寫 entity 形狀 —— 手寫的副本不會
// 隨後端變動, 後端改欄位時前端不會編譯失敗, 只會在 runtime 變成 undefined。
//
// **這裡只放平台契約要求後端一定要有的型別** (`Permission`、`Language`), 業務 entity
// (UserInfo、RoleInfo…) 不進來: 由用到它的模組在自己的 `types.ts` 以
// `Schema<"UserInfo">` (`@/shared/api/contract`) 命名, 刪掉模組時型別跟著一起消失。

import type { components } from "./generated/schema"

type Schemas = components["schemas"]

// ---- 權限 ----
// 後端的 Permission enum, 經 OpenAPI 自動同步 —— 新增權限**不必**改這裡。
export type Permission = Schemas["Permission"]

/**
 * 排除超級管理者萬用字元的權限聯集。
 *
 * 這不是角色頁實際可指派的完整清單; `GET /roles/permission-options` 會排除標成
 * `assignable=False` 的權限 (見各 module 的 permission metadata)。
 */
export type AssignablePermission = Exclude<Permission, "*">

// ---- 語系 ----
// 後端 shared/http/errors.py 的 Language enum, 經 `GET /languages/` 進入 OpenAPI。
// 新增語系**不必**改前端這一份清單; 漏跟上的地方會編譯失敗 (tests/shared/i18n/locale.test-d.ts)。
export type Language = Schemas["Language"]

// ---- 列表回應形狀 ----
// 對應後端 shared/http/schema.py 的 PaginatedResponse[T] / SimpleListResponse[T]。後端用 pydantic
// 泛型, OpenAPI 會為每個具體型別各展開一份 (RoleList、UserList…), 所以這裡用 TS 泛型重新表達,
// 讓呼叫端可以寫 `PaginatedResponse<RoleInfo>`。
//
// `has_next` / `has_previous` / `total_count` 必填 (後端 `get_page` 一律提供) —— 標成選填只會讓
// 「後端漏了這些欄位」變成一份看起來合法的「只有一頁」結果。
export type PaginatedResponse<T> = {
  list_data: T[]
  next_cursor?: string | null
  prev_cursor?: string | null
  has_next: boolean
  has_previous: boolean
  total_count: number
}

export type SimpleListResponse<T> = {
  list_data: T[]
  count: number
}
