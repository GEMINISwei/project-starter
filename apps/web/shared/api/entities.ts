// **跨模組**共用的 entity 型別，一律從 `generated/schema.d.ts` 衍生（後端 OpenAPI 產生的，
// `make gen-types`）。不要在這裡手寫 entity 形狀 —— 手寫的副本不會隨後端變動，後端改欄位時
// 前端不會編譯失敗，只會在 runtime 變成 undefined。
//
// 進不進這裡的判準是**有沒有第二個模組真的在用**：只有自己模組在用的（例如 items 的
// `ItemInfo`）留在該模組的 `types.ts`，這樣「整包刪掉一個模組」才不必回頭改 shared。
// 出現第二個使用者時再搬進來，並讓原模組改成 re-export。
//
// 各模組的 `types.ts` 另外放該畫面專屬的型別（篩選條件、表單值…）。

import type { components } from "./generated/schema"

type Schemas = components["schemas"]

// ---- 權限 ----
// 後端 app/permissions.py 的 Permission enum，經 OpenAPI 自動同步 —— 新增權限**不必**改這裡。
export type Permission = Schemas["Permission"]

/**
 * 排除超級管理者萬用字元的權限聯集。
 *
 * 這不是角色頁實際可指派的完整清單；`GET /permissions/` 還會排除
 * `users:update:any` 與 `push:send`（見各 module 的 permission metadata）。
 */
export type AssignablePermission = Exclude<Permission, "*">

export type PermissionInfo = Schemas["PermissionInfo"]

// ---- 語系 ----
// 後端 shared/http/errors.py 的 Language enum，經 `GET /languages/` 進入 OpenAPI。
// 新增語系**不必**改前端這一份清單；漏跟上的地方會編譯失敗（tests/shared/i18n/locale.test-d.ts）。
export type Language = Schemas["Language"]

// ---- 使用者 ----
export type UserInfo = Schemas["UserInfo"]

/** `GET /users/me` 的回應：目前登入者。 */
export type CurrentUser = Schemas["UserMe"]

/** `POST /users/login` 的回應。 */
export type AuthToken = Schemas["UserToken"]

// ---- 角色 ----
export type RoleInfo = Schemas["RoleInfo"]

// ---- WebSocket 事件 ----
// 由後端 `modules/realtime/schema.py` 的 enum 經 `GET /ws/events` 進入 OpenAPI。這是關鍵的
// 那一半：`WSManager` 用 `Record<WsEventType, handler>` 窮盡處理，後端增刪事件而前端沒跟上
// 會**編譯失敗**。
export type WsEventType = Schemas["WsEventType"]

// 訊息信封是手寫的（WS 訊息不經過 HTTP 回應，不會進 OpenAPI）。改後端 `WsEvent` 欄位時這裡要
// 一併更新 —— 欄位名由 `tests/shared/api/ws-event-contract.test.ts` 比對（它直接讀那支 .py），
// 型別仍然靠人。
//
// 請保持只有少量選填欄位。需要複雜結構時，改成「事件只帶 type + id，內容回頭打 REST 查」。
export type WsEvent = {
  type: WsEventType
  from_nickname?: string | null
  /** 沒有對應 REST 資源可查的事件所帶的文字內容（例如 SYSTEM_ANNOUNCEMENT 的公告）。 */
  message?: string | null
}

// ---- 列表回應形狀 ----
// 對應後端 shared/http/schema.py 的 PaginatedResponse[T] / SimpleListResponse[T]。後端用 pydantic
// 泛型，OpenAPI 會為每個具體型別各展開一份（RoleList、UserList…），所以這裡用 TS 泛型重新表達，
// 讓呼叫端可以寫 `PaginatedResponse<RoleInfo>`。
//
// `has_next` / `has_previous` / `total_count` 必填（後端 `get_page` 一律提供）—— 標成選填只會讓
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
