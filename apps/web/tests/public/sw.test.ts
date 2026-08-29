// @vitest-environment node

import fs from "node:fs"
import vm from "node:vm"
import { describe, expect, it, vi } from "vitest"

type WorkerListener = (event: Record<string, unknown>) => void

describe("push service worker", () => {
  it("頁面可見時把 push 訊息交給頁面顯示", async () => {
    const postMessage = vi.fn()
    const worker = loadWorker([{ focused: true, postMessage }])

    await worker.dispatch("push", {
      data: { json: () => ({ title: "測試", body: "內容" }) },
    })

    expect(postMessage).toHaveBeenCalledWith({
      type: "PUSH_NOTIFICATION",
      payload: { title: "測試", body: "內容" },
    })
    expect(worker.showNotification).not.toHaveBeenCalled()
  })

  it("沒有可見頁面時交給系統通知", async () => {
    const worker = loadWorker([])

    await worker.dispatch("push", {
      data: { json: () => ({ title: "背景通知", body: "內容", url: "/items" }) },
    })

    expect(worker.showNotification).toHaveBeenCalledWith(
      "背景通知",
      expect.objectContaining({ body: "內容", data: { url: "/items" } }),
    )
  })

  it("點擊通知會關閉通知並聚焦既有頁面", async () => {
    const focus = vi.fn().mockResolvedValue(undefined)
    const close = vi.fn()
    const worker = loadWorker([{ url: "http://localhost/items", focus }])

    await worker.dispatch("notificationclick", {
      notification: { close, data: { url: "/items" } },
    })

    expect(close).toHaveBeenCalledOnce()
    expect(focus).toHaveBeenCalledOnce()
    expect(worker.openWindow).not.toHaveBeenCalled()
  })
})

function loadWorker(clients: Array<Record<string, unknown>>) {
  const listeners = new Map<string, WorkerListener>()
  const showNotification = vi.fn().mockResolvedValue(undefined)
  const openWindow = vi.fn().mockResolvedValue(undefined)
  const context = {
    URL,
    caches: {
      keys: vi.fn().mockResolvedValue([]),
      open: vi.fn().mockResolvedValue({ match: vi.fn(), put: vi.fn() }),
      delete: vi.fn(),
    },
    fetch: vi.fn(),
    self: {
      location: { origin: "http://localhost" },
      skipWaiting: vi.fn(),
      clients: {
        claim: vi.fn(),
        matchAll: vi.fn().mockResolvedValue(clients),
        openWindow,
      },
      registration: { showNotification },
      addEventListener: (type: string, listener: WorkerListener) => listeners.set(type, listener),
    },
  }
  vm.runInNewContext(fs.readFileSync("public/sw.js", "utf8"), context)

  return {
    showNotification,
    openWindow,
    async dispatch(type: string, event: Record<string, unknown>) {
      let pending = Promise.resolve()
      listeners.get(type)?.({
        ...event,
        waitUntil: (promise: Promise<unknown>) => { pending = promise.then(() => undefined) },
      })
      await pending
    },
  }
}
