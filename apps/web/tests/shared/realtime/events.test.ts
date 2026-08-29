import { describe, expect, it } from "vitest"
import { SYSTEM_WS_EVENTS } from "@/shared/realtime/events"
import { sharedMessages } from "@/shared/i18n/messages"

describe("shared realtime events", () => {
  it("系統公告保留訊息並在缺少內容時提供預設值", () => {
    const toast = SYSTEM_WS_EVENTS.system_announcement.toast
    expect(toast({ type: "system_announcement", message: "維護中" }, "zh")).toEqual({
      message: "維護中",
      severity: "info",
    })
    // 斷言字典本身而不是再抄一次中文字面值 —— 抄一份的話，改文案要改兩個地方。
    expect(toast({ type: "system_announcement" }, "zh").message).toBe(sharedMessages.zh.systemNotice)
  })

  it("fallback 跟著語系走", () => {
    const toast = SYSTEM_WS_EVENTS.system_announcement.toast
    expect(toast({ type: "system_announcement" }, "en").message).toBe(sharedMessages.en.systemNotice)
  })
})
