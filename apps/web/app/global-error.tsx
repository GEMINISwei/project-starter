"use client"

import { translate } from "@/shared/i18n/dictionary"
import { useLocaleFromCookie } from "@/shared/i18n/context"
import { HTML_LANG } from "@/shared/i18n/locale"
import { appMessages } from "@/config/i18n"
import { DEFAULT_THEME } from "@/config/theme"
// token 與主題要在這裡再載一次。這一頁**取代** root layout，所以 layout.tsx 的 CSS import
// 不會出現在它的文件裡 —— 實測建置產物 `_global-error.html` 只連到元件樣式那個 chunk，
// 底下每一個 `var(--…)` 都是解不出來的。少了這幾行，錯誤頁會退回瀏覽器預設樣式。
//
// 主題**每一份都要載**（現在只有 default）：`data-theme` 選到哪一份是執行期的事，
// 之後多一份主題卻只載 default，錯誤頁會安靜地維持原本的配色（`check:tokens` 在守這件事）。
import "./tokens/primitives.css"
import "./tokens/semantic.css"
import "./themes/default.css"

type GlobalErrorProps = {
  error: Error & { digest?: string }
  reset: () => void
}

export default function GlobalError({ reset }: GlobalErrorProps) {
  // 這一頁在 root layout 之外渲染，拿不到 LocaleProvider，所以直接讀 cookie。
  const locale = useLocaleFromCookie()
  const t = translate(appMessages, locale)

  return (
    <html lang={HTML_LANG[locale]} data-theme={DEFAULT_THEME}>
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          background: "var(--color-bg-app)",
          color: "var(--color-text-body)",
          fontFamily: "var(--font-sans)",
        }}
      >
        <main
          style={{
            minHeight: "100vh",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "var(--space-6)",
          }}
        >
          <section
            style={{
              width: "100%",
              maxWidth: "var(--container-narrow)",
              textAlign: "center",
            }}
          >
            <h1
              style={{
                margin: 0,
                color: "var(--color-text-heading)",
                fontFamily: "var(--font-serif)",
                fontSize: "var(--fs-h1)",
                fontWeight: "var(--fw-medium)",
                lineHeight: "var(--lh-tight)",
              }}
            >
              {t("errorTitle")}
            </h1>
            <p
              style={{
                margin: "var(--space-4) 0 var(--space-6)",
                color: "var(--color-text-secondary)",
                fontSize: "var(--fs-base)",
                lineHeight: "var(--lh-normal)",
              }}
            >
              {t("errorDescription")}
            </p>
            <button
              type="button"
              onClick={reset}
              style={{
                minHeight: "var(--control-height-md)",
                padding: "0 var(--space-5)",
                border: "var(--border-width-hairline) solid var(--color-action-primary)",
                borderRadius: "var(--radius-md)",
                background: "var(--color-action-primary)",
                color: "var(--color-text-on-primary)",
                boxShadow: "var(--shadow-sm)",
                cursor: "pointer",
                fontFamily: "var(--font-sans)",
                fontSize: "var(--fs-sm)",
                fontWeight: "var(--fw-semibold)",
              }}
            >
              {t("retry")}
            </button>
          </section>
        </main>
      </body>
    </html>
  )
}
