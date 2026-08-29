"use client"

import { PageHeader } from "@/shared/ui"
import { useT } from "@/shared/i18n/context"
import { settingsMessages } from "../i18n"
import LanguageSettings from "./LanguageSettings"
import NotificationSettings from "./NotificationSettings"
import styles from "./settings.module.css"

export default function SettingsView() {
  const t = useT(settingsMessages)

  return (
    <div className={styles.page}>
      <PageHeader title={t("pageTitle")} />
      <div className={styles.content}>
        <LanguageSettings />
        <NotificationSettings />
      </div>
    </div>
  )
}
