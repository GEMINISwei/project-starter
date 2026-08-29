import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  registerServiceWorker,
  registerSubscriptionWithBackend,
  removeSubscriptionFromBackend,
  subscribeToPush,
  unsubscribeFromPush,
} from "@/modules/push/client"
import { registerPushSubscription, removePushSubscription } from "@/modules/push/actions"

// Server Action 一律 mock 掉：`actions.ts` 會拉進 `request.server.ts`，而那個模組帶
// `server-only`，在測試環境載入就會丟例外。這也符合專案慣例 —— actions 是薄 wrapper，
// 刻意不寫執行期測試（見 AGENTS.md）。這裡測的是 client 有沒有把正確的 payload 交給它們。
vi.mock("@/modules/push/actions", () => ({
  registerPushSubscription: vi.fn(),
  removePushSubscription: vi.fn(),
}))

const registerAction = vi.mocked(registerPushSubscription)
const removeAction = vi.mocked(removePushSubscription)

const originalServiceWorker = Object.getOwnPropertyDescriptor(navigator, "serviceWorker")

beforeEach(() => {
  registerAction.mockResolvedValue({ status: "success" } as never)
  removeAction.mockResolvedValue({ status: "success" } as never)
})

afterEach(() => {
  vi.restoreAllMocks()
  registerAction.mockReset()
  removeAction.mockReset()
  if (originalServiceWorker) {
    Object.defineProperty(navigator, "serviceWorker", originalServiceWorker)
  } else {
    Reflect.deleteProperty(navigator, "serviceWorker")
  }
})

describe("push client", () => {
  it("註冊 service worker 並沿用既有 push subscription", async () => {
    const existing = { endpoint: "https://push.example/existing" } as PushSubscription
    const registration = {
      pushManager: {
        getSubscription: vi.fn().mockResolvedValue(existing),
        subscribe: vi.fn(),
      },
    } as unknown as ServiceWorkerRegistration
    const register = vi.fn().mockResolvedValue(registration)
    setServiceWorker({ register })

    expect(await registerServiceWorker()).toBe(registration)
    expect(register).toHaveBeenCalledWith("/sw.js", { scope: "/" })
    expect(await subscribeToPush(registration, "AQAB")).toBe(existing)
    expect(registration.pushManager.subscribe).not.toHaveBeenCalled()
  })

  it("沒有既有訂閱時會用 VAPID key 建立 subscription", async () => {
    const created = { endpoint: "https://push.example/new" } as PushSubscription
    const subscribe = vi.fn().mockResolvedValue(created)
    const registration = {
      pushManager: {
        getSubscription: vi.fn().mockResolvedValue(null),
        subscribe,
      },
    } as unknown as ServiceWorkerRegistration

    expect(await subscribeToPush(registration, "AQAB")).toBe(created)
    expect(subscribe).toHaveBeenCalledWith({
      userVisibleOnly: true,
      applicationServerKey: new Uint8Array([1, 0, 1]),
    })
  })

  it("同步新增與刪除 subscription 到後端", async () => {
    const subscription = {
      toJSON: () => ({
        endpoint: "https://push.example/device",
        keys: { p256dh: "p256dh", auth: "auth" },
      }),
    } as unknown as PushSubscription

    expect(await registerSubscriptionWithBackend(subscription, "browser-agent")).toBe(true)
    expect(await removeSubscriptionFromBackend("https://push.example/device")).toBe(true)

    expect(registerAction).toHaveBeenCalledWith({
      endpoint: "https://push.example/device",
      p256dh: "p256dh",
      auth: "auth",
      user_agent: "browser-agent",
    })
    expect(removeAction).toHaveBeenCalledWith("https://push.example/device")
  })

  it("後端回報失敗時回傳 false，不當成成功", async () => {
    registerAction.mockResolvedValue({ status: "failure" } as never)
    const subscription = {
      toJSON: () => ({
        endpoint: "https://push.example/device",
        keys: { p256dh: "p256dh", auth: "auth" },
      }),
    } as unknown as PushSubscription

    expect(await registerSubscriptionWithBackend(subscription, "browser-agent")).toBe(false)
  })

  it("subscription 缺少金鑰時不送出請求", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const subscription = {
      toJSON: () => ({ endpoint: "https://push.example/device", keys: {} }),
    } as unknown as PushSubscription

    expect(await registerSubscriptionWithBackend(subscription, "browser-agent")).toBe(false)
    // 後端三個欄位都必填，缺了就送不出有效請求 —— 不要浪費一次往返去換 422。
    expect(registerAction).not.toHaveBeenCalled()
    expect(warn).toHaveBeenCalledOnce()
  })

  it("取消瀏覽器 subscription 並回傳 endpoint", async () => {
    const unsubscribe = vi.fn().mockResolvedValue(true)
    const subscription = {
      endpoint: "https://push.example/device",
      unsubscribe,
    } as unknown as PushSubscription
    const registration = {
      pushManager: { getSubscription: vi.fn().mockResolvedValue(subscription) },
    } as unknown as ServiceWorkerRegistration
    setServiceWorker({ ready: Promise.resolve(registration) })

    expect(await unsubscribeFromPush()).toBe("https://push.example/device")
    expect(unsubscribe).toHaveBeenCalledOnce()
  })

  it("瀏覽器不支援或 service worker 註冊失敗時安全退回 null", async () => {
    Reflect.deleteProperty(navigator, "serviceWorker")
    expect(await registerServiceWorker()).toBeNull()

    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    setServiceWorker({ register: vi.fn().mockRejectedValue(new Error("register failed")) })
    expect(await registerServiceWorker()).toBeNull()
    expect(warn).toHaveBeenCalledWith(
      "[push] registerServiceWorker failed",
      expect.any(Error),
    )
  })

  it("Push API 或後端同步失敗時不拋出例外", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {})
    const registration = {
      pushManager: {
        getSubscription: vi.fn().mockResolvedValue(null),
        subscribe: vi.fn().mockRejectedValue(new Error("subscribe failed")),
      },
    } as unknown as ServiceWorkerRegistration
    registerAction.mockRejectedValue(new Error("register request failed"))
    removeAction.mockRejectedValue(new Error("remove request failed"))
    const subscription = {
      toJSON: () => ({
        endpoint: "https://push.example/device",
        keys: { p256dh: "p256dh", auth: "auth" },
      }),
    } as unknown as PushSubscription

    expect(await subscribeToPush(registration, "AQAB")).toBeNull()
    expect(await registerSubscriptionWithBackend(subscription, "browser-agent")).toBe(false)
    expect(await removeSubscriptionFromBackend("https://push.example/device")).toBe(false)
    expect(warn).toHaveBeenCalledTimes(3)
  })

  it("沒有瀏覽器 subscription 時取消操作安全退回 null", async () => {
    const registration = {
      pushManager: { getSubscription: vi.fn().mockResolvedValue(null) },
    } as unknown as ServiceWorkerRegistration
    setServiceWorker({ ready: Promise.resolve(registration) })

    expect(await unsubscribeFromPush()).toBeNull()
  })
})

function setServiceWorker(value: Partial<ServiceWorkerContainer>) {
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value,
  })
}
