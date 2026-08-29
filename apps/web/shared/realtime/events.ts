/**
 * WebSocket 事件 → 畫面反應的型別，以及不屬於任何功能的通用事件處理。
 *
 * 每個功能各自提供自己的處理，再由 `WSManager` 合併。合併處仍標註
 * `Record<WsEventType, WsEventHandler>`，所以「後端加了事件、前端沒補」是**編譯失敗**。
 */

import type { NotifyState } from "@/shared/ui"
import type { WsEvent, WsEventType } from "@/shared/api/entities"
import { translate } from "@/shared/i18n/dictionary"
import type { Locale } from "@/shared/i18n/locale"
import { sharedMessages } from "@/shared/i18n/messages"

export type WsToast = {
  message: string
  severity: NonNullable<NotifyState["severity"]>
}

export type WsEventHandler = {
  /**
   * 收到事件時要顯示的提示。收 `locale` 而不是讓 `WSManager` 事後翻譯：文案有一半來自後端
   * （`event.message`，已依 Accept-Language 回應），把語系傳進來，兩半才會在同一處合起來。
   */
  toast: (event: WsEvent, locale: Locale) => WsToast
  /**
   * 事件專屬的額外副作用（例如通知某個列表重新抓資料）。
   * 選填；只有需要額外畫面反應的事件才宣告。
   */
  onReceive?: () => void
}

/** 通用事件的處理；不依賴任何功能模組，請隨 `WsEventType.SYSTEM_ANNOUNCEMENT` 一起保留。 */
export const SYSTEM_WS_EVENTS = {
  system_announcement: {
    toast: (event, locale) => ({
      message: event.message ?? translate(sharedMessages, locale)("systemNotice"),
      severity: "info",
    }),
  },
} satisfies Partial<Record<WsEventType, WsEventHandler>>
