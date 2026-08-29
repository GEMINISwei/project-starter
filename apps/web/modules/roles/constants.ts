// 權限勾選畫面（ui/PermissionChecklist.tsx）的顯示標籤與分類佈局。
//
// 抽出來是為了讓 key 綁上 `PermissionValue`：後端新增或改名權限、跑過 `make gen-types` 之後，
// 這裡漏了標籤會**編譯失敗**，而不是在畫面上靜靜顯示 `items:read` 這種原始字串。
//
// 用 `LocaleText`（中英兩份）而不是模組字典的 key：字典的 key 是任意字串，綁不住
// `PermissionValue` 這個聯集，換成字典就會失去那個編譯期保護。
import type { Translator } from "@/shared/i18n/dictionary"
import type { Locale, LocaleText } from "@/shared/i18n/locale"
import type { rolesMessages } from "./i18n"
import type { PermissionValue, RolePermissionValue, RoleInfo } from "./types"

/**
 * 權限的顯示文字。有分類標題的權限（見 `CATEGORY_LAYOUT`）只寫動詞，語境由標題提供；會落到
 * 「其他」的則寫完整標籤，否則畫面上看不出它屬於哪一類。
 *
 * `users:update:any` 與 `push:send` 是 `assignable=False`，不會出現在 `GET /permissions/` 的
 * 回應裡，永遠不會被渲染；列在這裡純粹是為了滿足窮盡檢查。
 */
const PERMISSION_ACTION_LABELS = {
  // users —— 由 CATEGORY_LAYOUT 的「使用者」標題提供語境
  "users:create": { zh: "建立", en: "Create" },
  "users:read": { zh: "查看", en: "View" },
  "users:update:own": { zh: "更新", en: "Update" },
  "users:update:any": { zh: "使用者：更新任意使用者", en: "Users: update any user" },
  "users:delete": { zh: "停用", en: "Disable" },
  "users:manage": { zh: "管理", en: "Manage" },
  // roles —— 由 CATEGORY_LAYOUT 的「角色」標題提供語境
  "roles:create": { zh: "建立", en: "Create" },
  "roles:read": { zh: "查看", en: "View" },
  "roles:update": { zh: "更新", en: "Update" },
  "roles:manage": { zh: "管理", en: "Manage" },
  // 未分類，會落到「其他」
  "items:read": { zh: "項目：查看", en: "Items: view" },
  "items:create": { zh: "項目：建立", en: "Items: create" },
  "items:update": { zh: "項目：更新", en: "Items: update" },
  "items:delete": { zh: "項目：刪除", en: "Items: delete" },
  "items:manage": { zh: "項目：管理", en: "Items: manage" },
  "push:send": { zh: "推播：廣播通知", en: "Push: broadcast" },
} as const satisfies Record<PermissionValue, LocaleText>

export function getPermissionActionLabel(value: RolePermissionValue, locale: Locale): string {
  // `*` 只有系統角色會有，不在可勾選清單裡，沒有對應的動詞標籤。
  if (value === "*") return value
  // 後端已改、前端還沒跑 `make gen-types` 時退回原始字串，不要顯示 undefined。
  return PERMISSION_ACTION_LABELS[value]?.[locale] ?? value
}

type CategoryLayout = {
  key: string
  label: LocaleText
  crud: PermissionValue[]      // 有序：建立 → 查看 → 更新* → 刪除/停用
  extended: PermissionValue[]  // 延伸功能（管理等）
  hidden?: boolean
}

export const CATEGORY_LAYOUT: CategoryLayout[] = [
  {
    key: "users",
    label: { zh: "使用者", en: "Users" },
    crud: ["users:create", "users:read", "users:update:own", "users:delete"],
    extended: ["users:manage"],
    hidden: true,
  },
  {
    key: "roles",
    label: { zh: "角色", en: "Roles" },
    crud: ["roles:create", "roles:read", "roles:update"],
    extended: ["roles:manage"],
    hidden: true,
  },
]

/**
 * 系統角色的顯示名稱。key 是後端 `modules/roles/model.py` 的 role code。
 *
 * 角色名存在 DB 裡而且使用者可以改，所以它是資料不是文案，做成雙語會污染資料模型。但 seed 出來
 * 的系統角色是**模板給的**，英文使用者不該看到「超級管理者」，所以在顯示這一層依 code 換掉。
 *
 * 刻意**不做窮盡檢查**（不像 `PERMISSION_ACTION_LABELS`）：後端沒有 role code 的 enum，下游也
 * 可以自己 seed 更多系統角色。認不出的 code 退回 DB 名稱是安全的降級。
 */
const SYSTEM_ROLE_NAME_KEYS = {
  super_admin: "roleSuperAdmin",
} as const satisfies Record<string, keyof (typeof rolesMessages)["zh"]>

/**
 * 角色在畫面上的名稱。系統角色走字典，其他角色用 DB 名稱。這個模組是唯一擁有者，users 模組經
 * `public.client.ts` 取用 —— 兩邊各寫一份的話，改了顯示規則只會有一邊跟上。
 */
export function getRoleDisplayName(
  role: Pick<RoleInfo, "code" | "name">,
  t: Translator<(typeof rolesMessages)["zh"]>,
): string {
  const key = role.code
    ? SYSTEM_ROLE_NAME_KEYS[role.code as keyof typeof SYSTEM_ROLE_NAME_KEYS]
    : undefined

  return key ? t(key) : role.name
}
