"use client"

import { useEffect, useRef, useState } from "react"
import { cls } from "../internals"
import styles from "../styles/action-menu.module.css"

/**
 * 選單本體的寬度與離視窗邊緣的最小間距。
 *
 * 位置要用 JS 算 (`position: fixed` 才不會被表格的 `overflow` 裁掉), 但寬度住在
 * CSS 的 `.dropdown { min-width }`。兩邊必須一致, 所以在這裡寫成有名字的常數並
 * 標明對應關係。**不要就地寫 `window.innerWidth - 148`** —— 改了 CSS 的 min-width
 * 就會讓右邊界的夾擠算錯, 而且不會有任何訊號。
 */
const DROPDOWN_WIDTH = 140
const VIEWPORT_MARGIN = 8
const TRIGGER_GAP = 4

export type MenuItem = {
  icon?: React.ReactNode
  label: string
  color?: "default" | "error"
  onClick: () => void
}

type MenuProps = {
  items: (MenuItem | null | false | undefined)[]
  /** 觸發按鈕裡的內容 (圖示、頭像…)。 */
  trigger: React.ReactNode
  /** 觸發按鈕的無障礙名稱: 內容只有圖示時, 這是唯一說得出它是什麼的地方。 */
  triggerLabel: string
  /** 觸發按鈕的外觀。沒給就用 kit 的圖示按鈕。 */
  triggerClassName?: string
  /** 貼在畫面底部的觸發點 (側欄底部、手機的底部導覽) 要往上展開, 否則選單會被切掉。 */
  placement?: "below" | "above"
  /** 撐滿外層 (例如側欄底部、底部導覽的一格); 預設跟內容一樣寬。 */
  fullWidth?: boolean
}

type Position = { left: number; top?: number; bottom?: number }

export default function Menu({
  items,
  trigger,
  triggerLabel,
  triggerClassName,
  placement = "below",
  fullWidth = false,
}: MenuProps) {
  const [open, setOpen] = useState(false)
  const [position, setPosition] = useState<Position>({ top: 0, left: 0 })
  const ref = useRef<HTMLDivElement>(null)
  const visibleItems = items.filter((item): item is MenuItem => Boolean(item))

  function toggleOpen() {
    if (!open && ref.current) {
      const rect = ref.current.getBoundingClientRect()
      const left = Math.min(
        Math.max(VIEWPORT_MARGIN, rect.left),
        window.innerWidth - DROPDOWN_WIDTH - VIEWPORT_MARGIN,
      )
      setPosition(
        placement === "above"
          ? { left, bottom: window.innerHeight - rect.top + TRIGGER_GAP }
          : { left, top: rect.bottom + TRIGGER_GAP },
      )
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
    <div ref={ref} className={cls(styles.wrapper, fullWidth && styles.wrapperFull)}>
      <button
        type="button"
        className={triggerClassName ?? styles.trigger}
        onClick={toggleOpen}
        aria-label={triggerLabel}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {trigger}
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
