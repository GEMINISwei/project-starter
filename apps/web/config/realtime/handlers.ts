import type { WsEventType } from "@/shared/api/entities"
import { ITEM_WS_EVENTS } from "@/modules/items/public.client"
import { SYSTEM_WS_EVENTS, type WsEventHandler } from "@/shared/realtime/events"

/**
 * 每個 WS 事件對應的畫面反應，由各功能各自提供的處理合併而成。
 *
 * 型別是 `Record<WsEventType, …>`（完整聯集，不是 Partial），所以這張表是**窮盡**的：
 * 後端在 `modules/realtime/schema.py` 新增事件而這裡沒補 → 少一個 key，`tsc` 失敗；
 * 後端刪掉事件而這裡沒刪 → 多一個 key，同樣失敗。
 */
export const EVENT_HANDLERS: Record<WsEventType, WsEventHandler> = {
  ...SYSTEM_WS_EVENTS,
  ...ITEM_WS_EVENTS,
}
