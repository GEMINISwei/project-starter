import { apiGet } from "@/shared/api/request.server"

// 系統初始化狀態。login 與 signup 兩頁都靠它決定「該不該把人導去另一頁」。
//
// 刻意回傳三態而不是 boolean：兩頁對「查不到」的正確處置方向相反。
// signup 查不到時要顯示表單（後端才是最終把關者），login 查不到時要留在原地
// （後端抖一下不該把所有訪客踢去註冊）。壓成 boolean 就一定有一頁是錯的。
export type BootstrapState = "available" | "completed" | "unknown"

export async function getBootstrapState(): Promise<BootstrapState> {
  const status = await apiGet({
    url: "/users/bootstrap-status",
    auth: "none",
  })

  if (status.status !== "success") return "unknown"

  return status.data.available ? "available" : "completed"
}
