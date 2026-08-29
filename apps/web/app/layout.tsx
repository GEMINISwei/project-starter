import type { Metadata } from "next"
import { Noto_Sans_TC, Noto_Serif_TC } from "next/font/google"
import { NotifyViewport } from "@/shared/ui"
import { HTML_LANG } from "@/shared/i18n/locale"
import { getLocale } from "@/shared/i18n/locale.server"
import { LocaleProvider } from "@/shared/i18n/context"
import { getPublicConfig } from "@/shared/runtime/config.server"
import { PublicConfigProvider } from "@/shared/runtime/context"
import { DEFAULT_THEME } from "@/config/theme"
// 順序有意義：原始值 → 語意 → 主題 → reset。目前只有一份主題；多一份時每一份都要
// 載入，實際生效的由 <html> 的 data-theme 決定（見 docs/design-system.md）。
import "./tokens/primitives.css"
import "./tokens/semantic.css"
import "./themes/default.css"
import "./globals.css"
import "@/shared/ui/styles/message-page.css"

/**
 * 字型走 `next/font` 而不是 globals.css 的 `@import url(fonts.googleapis.com)`：`@import` 是
 * render-blocking 的第三方請求，首屏多等一個 round trip 而且字型換上來時會跳版。`next/font`
 * 在建置期把檔案抓下來自架、自動產生 `size-adjust` 的 fallback。
 *
 * `preload: false`：CJK 字型有數十個 unicode-range 分片，preload 會把整組都塞進 `<head>`。
 */
const sans = Noto_Sans_TC({
  weight: ["400", "500", "600", "700"],
  display: "swap",
  preload: false,
  variable: "--font-sans-loaded",
})

const serif = Noto_Serif_TC({
  weight: ["400", "500", "700"],
  display: "swap",
  preload: false,
  variable: "--font-serif-loaded",
})

// 用 `generateMetadata` 而不是靜態的 `metadata`：標題來自執行期的環境變數，而靜態 metadata 會
// 在預先渲染的頁面上於 build 期定案（同 `shared/runtime/config.ts` 要解決的問題）。
export async function generateMetadata(): Promise<Metadata> {
  const { systemName } = getPublicConfig()

  return {
    title: {
      default: systemName,
      template: `%s | ${systemName}`,
    },
    description: "",
    icons: {
      icon: [
        { url: "/favicon.ico", sizes: "any" },
        { url: "/app-icon-192.png", sizes: "192x192", type: "image/png" },
        { url: "/app-icon-512.png", sizes: "512x512", type: "image/png" },
      ],
      apple: [
        { url: "/app-icon-192.png", sizes: "192x192" },
        { url: "/app-icon-1024.png", sizes: "1024x1024" },
      ],
    },
  }
}

export default async function RootLayout({ children }: React.PropsWithChildren) {
  const locale = await getLocale()
  const publicConfig = getPublicConfig()

  return (
    <html
      lang={HTML_LANG[locale]}
      data-theme={DEFAULT_THEME}
      className={`${sans.variable} ${serif.variable}`}
    >
      <body>
        {/* provider 只帶語系代號，字典由各元件自己 import（見 shared/i18n/context.tsx）。 */}
        <LocaleProvider locale={locale}>
          {/* 公開設定只有這一個注入點；client component 一律走 usePublicConfig()。 */}
          <PublicConfigProvider config={publicConfig}>
            {children}
            <NotifyViewport />
          </PublicConfigProvider>
        </LocaleProvider>
      </body>
    </html>
  )
}
