import Link from "next/link"
import type { ReactNode } from "react"

// 全頁訊息（錯誤、404）的共用外觀。樣式由 root layout 載入，避免 Next.js dev
// 將共用 CSS 拆成 error/not-found 專屬 preload chunk。
//
// 註：app/global-error.tsx 刻意**不**使用這個元件。那支會取代整個 root layout（含 html/body），
// 執行當下不保證 CSS 已經載入，所以它必須維持自帶 inline style。

type MessagePageProps = {
  title: string
  description: string
  /** 巢狀在 AppShell 內時用 true：外層已經撐滿視窗，這裡只要填滿容器。 */
  inline?: boolean
  children?: ReactNode
}

export function MessagePage({ title, description, inline, children }: MessagePageProps) {
  return (
    <main className={`message-page${inline ? " message-page--inline" : ""}`}>
      <section className="message-page__panel">
        <h2 className="message-page__title">{title}</h2>
        <p className="message-page__description">{description}</p>
        <div className="message-page__actions">{children}</div>
      </section>
    </main>
  )
}

export function MessagePageButton({
  onClick,
  children,
}: {
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="message-page__action message-page__action--primary"
    >
      {children}
    </button>
  )
}

export function MessagePageLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="message-page__action message-page__action--secondary">
      {children}
    </Link>
  )
}
