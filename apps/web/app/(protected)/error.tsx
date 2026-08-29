"use client"

import { MessagePage, MessagePageButton, MessagePageLink } from "@/shared/ui"
import { useT } from "@/shared/i18n/context"
import { appMessages } from "@/config/i18n"

type ProtectedErrorBoundaryProps = {
  error: Error & { digest?: string }
  reset: () => void
}

export default function ProtectedErrorBoundary({ reset }: ProtectedErrorBoundaryProps) {
  const t = useT(appMessages)

  // inline：這層在 AppShell 內部，外框已經撐滿視窗。
  return (
    <MessagePage inline title={t("pageErrorTitle")} description={t("pageErrorDescription")}>
      <MessagePageButton onClick={reset}>{t("reload")}</MessagePageButton>
      <MessagePageLink href="/">{t("backHome")}</MessagePageLink>
    </MessagePage>
  )
}
