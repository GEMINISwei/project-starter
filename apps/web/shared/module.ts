import type { Permission } from "@/shared/api/entities"
import type { LocaleText } from "@/shared/i18n/locale"

export type RouteArea = "admin" | "user"

export type ProtectedRoute = {
  path: string
  /**
   * 導覽列顯示的名稱, 中英兩份。不走字典的 key: manifest 必須保持 edge-safe (`proxy.ts` 會經由
   * `config/routes.ts` 載入它), 而查字典需要的 React context 在那一層不存在。
   */
  label: LocaleText
  /** 掛在哪一區: `app/(protected)/admin` (網址帶 `/admin`) 或 `app/(protected)/(user)`, 兩區各有自己的外殼與導覽。 */
  group: RouteArea
  requires: readonly Permission[]
  navIcon: string
  /**
   * 要不要出現在導覽列。`false` 的路由一樣受保護 (proxy 與外殼照常套用), 只是入口在別處
   * —— 例如設定頁的入口在頭像選單。刻意不做成選填, 理由同 `protectedRoutes`。
   */
  showInNav: boolean
}

export type ModuleManifest = {
  name: string
  /**
   * 這個模組要掛上的受保護路由。**沒有頁面的模組寫 `[]`**, 刻意不做成選填: `config/routes.ts`
   * 要從這份清單推導型別聯集 (欄位可有可無會讓推導斷掉), 而且選填會讓「沒有頁面」與
   * 「作者忘了寫」看起來一模一樣。
   */
  protectedRoutes: readonly ProtectedRoute[]
}
