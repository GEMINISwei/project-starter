// 這裡每個函式在失敗時都回傳 null/false 而不是 throw：推播是「有更好、沒有也不影響主要功能」
// 的加值功能，不該讓它把整個畫面弄壞。但**靜默**吞掉錯誤會讓使用者回報「推播沒作用」時
// 完全無從查起，所以一律留下 console.warn。
//
// **這個檔案只放真的需要瀏覽器 API 的東西**（Service Worker、PushManager）。
// 與後端的往來一律走 `./actions.ts` 的 Server Action —— 直接在這裡 fetch 後端，
// 等於繞過 OpenAPI 推導的型別契約，理由見 actions.ts 開頭。
import { registerPushSubscription, removePushSubscription } from "./actions"
import { urlBase64ToUint8Array } from "./encoding"

function warn(action: string, error: unknown) {
  console.warn(`[push] ${action} failed`, error)
}

export async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!("serviceWorker" in navigator)) return null
  try {
    return await navigator.serviceWorker.register("/sw.js", { scope: "/" })
  } catch (error) {
    warn("registerServiceWorker", error)
    return null
  }
}

export async function subscribeToPush(
  registration: ServiceWorkerRegistration,
  vapidPublicKey: string,
): Promise<PushSubscription | null> {
  try {
    const existing = await registration.pushManager.getSubscription()
    if (existing) return existing
    return await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapidPublicKey),
    })
  } catch (error) {
    warn("subscribeToPush", error)
    return null
  }
}

export async function registerSubscriptionWithBackend(
  sub: PushSubscription,
  userAgent: string,
): Promise<boolean> {
  const subJson = sub.toJSON()
  // PushSubscription.toJSON() 的 endpoint 與 keys 在型別上都是選填（規格允許），
  // 但後端三個欄位都必填。缺了就不必送 —— 送出去只會拿到 422。
  if (!subJson.endpoint || !subJson.keys?.p256dh || !subJson.keys?.auth) {
    warn("registerSubscriptionWithBackend", new Error("subscription 缺少 endpoint 或金鑰"))
    return false
  }

  try {
    const res = await registerPushSubscription({
      endpoint: subJson.endpoint,
      p256dh: subJson.keys.p256dh,
      auth: subJson.keys.auth,
      user_agent: userAgent,
    })
    return res.status === "success"
  } catch (error) {
    warn("registerSubscriptionWithBackend", error)
    return false
  }
}

export async function unsubscribeFromPush(): Promise<string | null> {
  if (!("serviceWorker" in navigator)) return null
  try {
    const reg = await navigator.serviceWorker.ready
    const sub = await reg.pushManager.getSubscription()
    if (!sub) return null
    const endpoint = sub.endpoint
    await sub.unsubscribe()
    return endpoint
  } catch (error) {
    warn("unsubscribeFromPush", error)
    return null
  }
}

export async function removeSubscriptionFromBackend(endpoint: string): Promise<boolean> {
  try {
    const res = await removePushSubscription(endpoint)
    return res.status === "success"
  } catch (error) {
    warn("removeSubscriptionFromBackend", error)
    return false
  }
}
