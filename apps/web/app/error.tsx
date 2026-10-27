"use client"

import { MessagePage, MessagePageButton, MessagePageLink } from "@/shared/ui"
import { useT } from "@/shared/i18n/context"
import { appMessages } from "@/config/i18n"

type ErrorBoundaryProps = {
  error: Error & { digest?: string }
  reset: () => void
  /** 畫在外殼裡面時用 (見 `(protected)/area-error.tsx`)。Next 不會傳這個值。 */
  inline?: boolean
}

export default function ErrorBoundary({ reset, inline = false }: ErrorBoundaryProps) {
  const t = useT(appMessages)

  return (
    <MessagePage inline={inline} title={t("pageErrorTitle")} description={t("pageErrorDescription")}>
      <MessagePageButton onClick={reset}>{t("reload")}</MessagePageButton>
      <MessagePageLink href="/">{t("backHome")}</MessagePageLink>
    </MessagePage>
  )
}
