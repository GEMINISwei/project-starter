/**
 * **範例模組**的 WebSocket 事件處理。用不到時整包刪除，見 docs/architecture.md「移除 module」。
 *
 * 處理表刻意依功能分檔：文案與副作用住在功能目錄底下，共用殼層 `WSManager.tsx` 只負責合併成
 * 完整的 `Record<WsEventType, …>` —— 刪掉一個功能不必動共用元件，殼層也不認識任何 domain。
 *
 * 這裡沒有宣告 `onReceive`：項目是使用者自己透過 Server Action 建立的，那條路徑已經帶了
 * `refresh`。需要「別人改了資料、我這邊要重抓」的功能才會用到它。
 */

import { translate } from "@/shared/i18n/dictionary"
import type { WsEventHandler } from "@/shared/realtime/events"
import type { WsEventType } from "@/shared/api/entities"
import { itemsMessages } from "./i18n"

export const ITEM_WS_EVENTS = {
  item_created: {
    toast: (event, locale) => ({
      // 正常情況下走後端的 message：已依 Accept-Language 組好且帶著項目名稱（見
      // `modules/items/service.py` 的 ITEM_CREATED_MESSAGE）。字典那一半是「舊版部署送來沒有
      // message 的事件」的退路，不是主要路徑。
      message: event.message ?? translate(itemsMessages, locale)("itemCreated"),
      severity: "success",
    }),
  },
} satisfies Partial<Record<WsEventType, WsEventHandler>>
