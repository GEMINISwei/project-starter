import "server-only"
import { apiGet } from "@/shared/api/request.server"

/**
 * 填下拉選單用的完整角色清單 (非分頁的 `GET /roles/options`)。
 *
 * 端點屬於 roles, 別的模組 (users 的篩選與指派) 經 public entry 取用, 不直接寫 URL ——
 * roles 改端點時只需要改這裡。錯誤訊息由呼叫端決定 (文案屬於呼叫端的畫面)。
 */
export function getRoleOptions() {
  return apiGet({ url: "/roles/options" })
}
