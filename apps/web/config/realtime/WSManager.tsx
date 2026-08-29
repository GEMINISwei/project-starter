"use client"

import { useEffect, useRef, useState } from "react"
import { Notify } from "@/shared/ui"
import { useLocale } from "@/shared/i18n/context"
import type { WsEvent } from "@/shared/api/entities"
import { requestWsTicket } from "@/shared/realtime/actions.server"
import { EVENT_HANDLERS } from "@/config/realtime/handlers"
import type { WsToast } from "@/shared/realtime/events"

function isKnownEvent(value: unknown): value is WsEvent {
  if (typeof value !== "object" || value === null) return false

  const { type } = value as { type?: unknown }

  return typeof type === "string" && Object.hasOwn(EVENT_HANDLERS, type)
}

export default function WSManager() {
  const locale = useLocale()
  const [wsNotify, setWsNotify] = useState<WsToast | null>(null)
  // 語系走 ref 而不是進 effect 的依賴陣列：語系是 toast 文案的參數，不是連線的參數。
  // 放進依賴會讓「切換語言」變成「斷線重連」，而重連要重新換一張 ticket。
  const localeRef = useRef(locale)
  useEffect(() => {
    localeRef.current = locale
  }, [locale])

  useEffect(() => {
    // WS 位址一律由目前的 origin 推導：所有流量都走同一個 nginx，
    // 不需要（也不該）把後端位址編進 client bundle。
    const wsBase = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}`

    let ws: WebSocket | null = null
    let retryCount = 0
    let retryTimeout: ReturnType<typeof setTimeout> | null = null
    let intentionallyClosed = false
    const MAX_RETRY = 8

    async function connect() {
      // 每次連線（含重連）都重新換一張 ticket —— ticket 是短效的，
      // 放著重複使用會在重連時已經過期。
      const ticket = await requestWsTicket()
      if (intentionallyClosed) return
      if (!ticket) {
        scheduleRetry()
        return
      }

      ws = new WebSocket(`${wsBase}/api/ws?ticket=${encodeURIComponent(ticket)}`)

      ws.onopen = () => {
        retryCount = 0
      }

      ws.onmessage = (message) => {
        try {
          const data: unknown = JSON.parse(message.data)
          // 忽略未辨識事件，避免瀏覽器仍載入不同部署版本時中斷連線處理。
          // 原始碼的事件完整性由 EVENT_HANDLERS 的窮盡型別檢查保證。
          if (!isKnownEvent(data)) return

          const handler = EVENT_HANDLERS[data.type]
          setWsNotify(handler.toast(data, localeRef.current))
          // 副作用由各事件自行宣告，避免非相關事件觸發資料重查。
          handler.onReceive?.()
        } catch {
          // 收到不是 JSON 的訊息就丟掉。這裡不能讓例外往外跑：onmessage 拋出來會終結
          // 這一條連線，等於一個壞封包就讓整個即時推送靜靜停掉。
        }
      }

      ws.onclose = () => {
        scheduleRetry()
      }

      ws.onerror = () => {
        // 靜默忽略，onclose 負責重連
      }
    }

    function scheduleRetry() {
      if (intentionallyClosed || retryCount >= MAX_RETRY) return
      const delay = Math.min(1000 * 2 ** retryCount, 30000)
      retryCount++
      retryTimeout = setTimeout(() => void connect(), delay)
    }

    void connect()

    return () => {
      intentionallyClosed = true
      if (retryTimeout !== null) clearTimeout(retryTimeout)
      if (ws) {
        if (ws.readyState === WebSocket.CONNECTING) {
          ws.onopen = () => ws?.close()
        } else {
          ws.close()
        }
      }
    }
  }, [])

  return (
    <Notify
      open={!!wsNotify}
      message={wsNotify?.message ?? ""}
      severity={wsNotify?.severity ?? "info"}
      onOpenChange={() => setWsNotify(null)}
    />
  )
}
