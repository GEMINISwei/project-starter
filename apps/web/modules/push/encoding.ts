/** 將沒有 padding 的 VAPID base64url 公鑰轉成 Push API 接受的位元組。 */
export function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64.length % 4)) % 4)
  const base64Std = (base64 + padding).replace(/-/g, "+").replace(/_/g, "/")
  const rawData = window.atob(base64Std)
  const buffer = new ArrayBuffer(rawData.length)
  const view = new Uint8Array(buffer)
  for (let i = 0; i < rawData.length; i++) {
    view[i] = rawData.charCodeAt(i)
  }
  return view
}
