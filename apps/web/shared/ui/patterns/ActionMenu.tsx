"use client"

import { useEffect, useRef, useState } from "react"
import { MoreVertical } from "lucide-react"
import { useT } from "@/shared/i18n/context"
import { uiMessages } from "../i18n"
import { cls } from "../internals"
import { ICON_SIZE } from "../internals"
import styles from "../styles/action-menu.module.css"

/**
 * 選單本體的寬度與離視窗邊緣的最小間距。
 *
 * 位置要用 JS 算（`position: fixed` 才不會被表格的 `overflow` 裁掉），但寬度住在
 * CSS 的 `.dropdown { min-width }`。兩邊必須一致，所以在這裡寫成有名字的常數並
 * 標明對應關係。**不要就地寫 `window.innerWidth - 148`** —— 改了 CSS 的 min-width
 * 就會讓右邊界的夾擠算錯，而且不會有任何訊號。
 */
const DROPDOWN_WIDTH = 140
const VIEWPORT_MARGIN = 8

export type ActionMenuItem = {
  icon?: React.ReactNode
  label: string
  color?: "default" | "error"
  onClick: () => void
}

type ActionMenuProps = {
  items: (ActionMenuItem | null | false | undefined)[]
}

export default function ActionMenu({ items }: ActionMenuProps) {
  const t = useT(uiMessages)
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState({ top: 0, left: 0 })
  const ref = useRef<HTMLDivElement>(null)
  const visibleItems = items.filter((item): item is ActionMenuItem => Boolean(item))

  function toggleOpen() {
    if (!open && ref.current) {
      const rect = ref.current.getBoundingClientRect()
      setPosition({
        top: rect.bottom + 4,
        left: Math.min(
          Math.max(VIEWPORT_MARGIN, rect.left),
          window.innerWidth - DROPDOWN_WIDTH - VIEWPORT_MARGIN,
        ),
      })
    }
    setOpen((current) => !current)
  }

  useEffect(() => {
    if (!open) return

    function handleClick(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }

    function handleScroll() {
      setOpen(false)
    }

    document.addEventListener("mousedown", handleClick)
    window.addEventListener("scroll", handleScroll, true)
    return () => {
      document.removeEventListener("mousedown", handleClick)
      window.removeEventListener("scroll", handleScroll, true)
    }
  }, [open])

  if (visibleItems.length === 0) return null

  return (
    <div ref={ref} className={styles.wrapper}>
      <button
        type="button"
        className={styles.trigger}
        onClick={toggleOpen}
        aria-label={t("actionMenu")}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <MoreVertical size={ICON_SIZE.sm} />
      </button>
      {open && (
        <div className={styles.dropdown} role="menu" style={position}>
          {visibleItems.map((item, index) => (
            <button
              key={index}
              type="button"
              role="menuitem"
              className={cls(styles.item, item.color === "error" && styles.itemError)}
              onClick={() => {
                setOpen(false)
                item.onClick()
              }}
            >
              {item.icon && <span className={styles.itemIcon}>{item.icon}</span>}
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
