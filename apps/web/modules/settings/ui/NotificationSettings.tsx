"use client"

import { useEffect, useState } from "react"
import {
  registerServiceWorker,
  registerSubscriptionWithBackend,
  removeSubscriptionFromBackend,
  subscribeToPush,
  unsubscribeFromPush,
} from "@/modules/push/public.client"
import { useT } from "@/shared/i18n/context"
import { usePublicConfig } from "@/shared/runtime/context"
import { settingsMessages } from "../i18n"
import styles from "./settings.module.css"

type PermissionState = NotificationPermission | "unsupported" | null

export default function NotificationSettings() {
  const t = useT(settingsMessages)
  const [permission, setPermission] = useState<PermissionState>(null)
  const [isSubscribed, setIsSubscribed] = useState<boolean | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const { vapidPublicKey: vapidKey } = usePublicConfig()

  useEffect(() => {
    function checkPermission() {
      if (!("Notification" in window)) {
        setPermission("unsupported")
        setIsSubscribed(false)
        return
      }
      const perm = Notification.permission
      setPermission(perm)
      if (perm === "granted" && "serviceWorker" in navigator) {
        navigator.serviceWorker.ready
          .then((reg) => reg.pushManager.getSubscription())
          .then((sub) => setIsSubscribed(!!sub))
          .catch(() => setIsSubscribed(false))
      } else {
        setIsSubscribed(false)
      }
    }

    checkPermission()

    function handleVisibilityChange() {
      if (document.visibilityState === "visible") {
        checkPermission()
      }
    }

    document.addEventListener("visibilitychange", handleVisibilityChange)
    return () => document.removeEventListener("visibilitychange", handleVisibilityChange)
  }, [])

  async function handleEnable() {
    if (!vapidKey || !("Notification" in window)) return
    setIsLoading(true)
    try {
      if (Notification.permission !== "granted") {
        const result = await Notification.requestPermission()
        setPermission(result)
        if (result !== "granted") return
      }
      const reg = await registerServiceWorker()
      if (!reg) return
      const sub = await subscribeToPush(reg, vapidKey)
      if (sub) {
        await registerSubscriptionWithBackend(sub, navigator.userAgent)
        setIsSubscribed(true)
      }
    } finally {
      setIsLoading(false)
    }
  }

  async function handleDisable() {
    setIsLoading(true)
    try {
      const endpoint = await unsubscribeFromPush()
      if (endpoint) await removeSubscriptionFromBackend(endpoint)
      setIsSubscribed(false)
    } finally {
      setIsLoading(false)
    }
  }

  const showToggle =
    permission !== null &&
    permission !== "unsupported" &&
    permission !== "denied"

  return (
    <section className={styles.section}>
      <h2 className={styles.sectionTitle}>{t("notificationSection")}</h2>
      <div className={styles.settingRow}>
        <div className={styles.settingInfo}>
          <span className={styles.settingName}>{t("pushNotification")}</span>
          {permission === "unsupported" && (
            <span className={styles.settingDesc}>{t("pushUnsupported")}</span>
          )}
          {permission === "denied" && (
            <span className={styles.settingDesc}>{t("pushDenied")}</span>
          )}
        </div>
        {showToggle && (
          <div className={styles.settingAction}>
            <label className={styles.toggle}>
              <input
                type="checkbox"
                className={styles.toggleInput}
                checked={isSubscribed === true}
                disabled={isLoading || isSubscribed === null}
                onChange={(e) =>
                  e.target.checked ? handleEnable() : handleDisable()
                }
              />
              <span className={styles.toggleSlider} />
            </label>
          </div>
        )}
      </div>
    </section>
  )
}
