import type { Permission } from "@/shared/api/entities"
import type { LocaleText } from "@/shared/i18n/locale"

export type ProtectedRoute = {
  path: string
  /**
   * 導覽列顯示的名稱，中英兩份。不走字典的 key：manifest 必須保持 edge-safe（`proxy.ts` 會經由
   * `config/routes.ts` 載入它），而查字典需要的 React context 在那一層不存在。
   */
  label: LocaleText
  group: "admin" | "general"
  requires: readonly Permission[]
  navIcon: string
}

export type ModuleManifest = {
  name: string
  /**
   * 這個模組要掛上的受保護路由。**沒有頁面的模組寫 `[]`**，刻意不做成選填：`config/routes.ts`
   * 要從這份清單推導型別聯集（欄位可有可無會讓推導斷掉），而且選填會讓「沒有頁面」與
   * 「作者忘了寫」看起來一模一樣。
   */
  protectedRoutes: readonly ProtectedRoute[]
}
