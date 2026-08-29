"use client"

import { useEffect, useState } from "react"
import { X } from "lucide-react"
import { ICON_SIZE } from "@/shared/ui"
import { useT } from "@/shared/i18n/context"
import { usePublicConfig } from "@/shared/runtime/context"
import { pushMessages } from "../i18n"
import {
  registerServiceWorker,
  registerSubscriptionWithBackend,
  subscribeToPush,
} from "../client"
import styles from "./push.module.css"

type PushMessage = {
  title?: string
  body?: string
  url?: string
}

export default function PushNotificationManager() {
  const t = useT(pushMessages)
  const [message, setMessage] = useState<PushMessage | null>(null)
  const { vapidPublicKey } = usePublicConfig()

  useEffect(() => {
    let mounted = true

    async function setupServiceWorker() {
      const registration = await registerServiceWorker()
      if (!mounted || !registration) return
      if ("Notification" in window && Notification.permission === "granted" && vapidPublicKey) {
        const subscription = await subscribeToPush(registration, vapidPublicKey)
        if (subscription) {
          await registerSubscriptionWithBackend(subscription, navigator.userAgent)
        }
      }
    }

    setupServiceWorker()

    function handleMessage(event: MessageEvent) {
      if (event.data?.type === "PUSH_NOTIFICATION") {
        setMessage(event.data.payload)
      }
    }

    navigator.serviceWorker?.addEventListener("message", handleMessage)
    return () => {
      mounted = false
      navigator.serviceWorker?.removeEventListener("message", handleMessage)
    }
  }, [vapidPublicKey])

  useEffect(() => {
    if (!message) return
    const timer = window.setTimeout(() => setMessage(null), 5000)
    return () => window.clearTimeout(timer)
  }, [message])

  if (!message) return null

  return (
    <div className={styles.pushToast} role="status">
      <div>
        <strong>{message.title ?? t("defaultTitle")}</strong>
        {message.body && <span>{message.body}</span>}
      </div>
      <button
        type="button"
        className={styles.pushToastClose}
        aria-label={t("closeNotification")}
        title={t("closeNotification")}
        onClick={() => setMessage(null)}
      >
        <X size={ICON_SIZE.sm} />
      </button>
    </div>
  )
}
