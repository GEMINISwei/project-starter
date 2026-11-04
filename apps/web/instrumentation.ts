/**
 * Next 的啟動掛勾。擋「image 裡的值」與「執行期給的值」對不起來的事 —— 那是**沒有症狀**的
 * 失敗, 所以要在開機當下就吵。
 */
export async function register() {
  // 動態 import 包在這個判斷裡: Next 才不會把 Node 專用的 API 編進 Edge 版本, build 與每個請求都報警告。
  if (process.env.NEXT_RUNTIME === "nodejs") {
    const { requireActionsEncryptionKey } = await import("@/shared/runtime/actions-key")
    requireActionsEncryptionKey()
  }
}
