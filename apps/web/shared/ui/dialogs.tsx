"use client"

import type { FormEvent, ReactNode } from "react"
import { useEffect, useRef } from "react"
import { X } from "lucide-react"
import { useT } from "@/shared/i18n/context"
import { FOCUSABLE_SELECTOR, ICON_SIZE } from "./internals"
import styles from "./styles/primitives.module.css"
import { uiMessages } from "./i18n"
import { Button } from "./primitives"

type ModalProps = {
  title?: string
  open: boolean
  children?: ReactNode
  width?: number
  onOpenChange?: (open: boolean) => void
}

export function Modal({ title, open, children, width, onOpenChange }: ModalProps) {
  const t = useT(uiMessages)
  const onOpenChangeRef = useRef(onOpenChange)
  const dialogRef = useRef<HTMLElement>(null)

  useEffect(() => { onOpenChangeRef.current = onOpenChange }, [onOpenChange])
  useEffect(() => {
    if (!open) return
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onOpenChangeRef.current?.(false)
      if (event.key === "Tab" && dialogRef.current) keepTabInside(dialogRef.current, event)
    }
    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [open])
  useEffect(() => {
    if (!open) return
    // 開啟前的焦點 (通常是觸發的按鈕), 關閉時還回去: 只用鍵盤的人才回得到原本那一列。
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const node = dialogRef.current
    if (node && !node.contains(document.activeElement)) {
      const target = node.querySelector<HTMLElement>("[autofocus]") ?? node
      target.focus({ preventScroll: true })
    }
    return () => {
      if (previous?.isConnected) previous.focus({ preventScroll: true })
    }
  }, [open])

  if (!open) return null
  return (
    <div className={styles.overlay} role="presentation" onMouseDown={() => onOpenChange?.(false)}>
      <section
        ref={dialogRef}
        tabIndex={-1}
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        style={{ width: width ? `min(100%, ${width}px)` : undefined }}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className={styles.modalHeader}>
          <h2 className={styles.modalTitle}>{title}</h2>
          <button type="button" className={styles.modalClose} aria-label={t("close")} onClick={() => onOpenChange?.(false)}>
            <X size={ICON_SIZE.sm} aria-hidden="true" />
          </button>
        </div>
        <div className={styles.modalBody}>{children}</div>
      </section>
    </div>
  )
}

/** `aria-modal` 的對話框: Tab 在最後一個 (Shift+Tab 在第一個) 可聚焦元素時繞回另一端, 不跑到背景。 */
function keepTabInside(container: HTMLElement, event: KeyboardEvent) {
  const focusable = [...container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)]
  const first = focusable[0]
  const last = focusable.at(-1)
  if (!first || !last) return
  const active = document.activeElement
  if (event.shiftKey && (active === first || active === container)) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
}

type FormDialogProps = {
  title: string
  open: boolean
  isPending: boolean
  submitText: string
  pendingText?: string
  onClose: () => void
  onSubmit: (event: FormEvent<HTMLFormElement>) => void
  children: ReactNode
}

export function FormDialog({
  title,
  open,
  isPending,
  submitText,
  pendingText,
  onClose,
  onSubmit,
  children,
}: FormDialogProps) {
  const t = useT(uiMessages)
  return (
    <Modal title={title} open={open} onOpenChange={(next) => { if (!next) onClose() }}>
      {/* 不跑原生驗證: 它的提示跟著瀏覽器語系而不是應用語系, 錯誤由各對話框標在欄位上。 */}
      <form className={styles.dialogForm} onSubmit={onSubmit} noValidate>
        {children}
        <div className={styles.dialogFormActions}>
          <Button variant="outlined" disabled={isPending} onClick={onClose}>{t("cancel")}</Button>
          <Button type="submit" disabled={isPending}>{isPending ? pendingText ?? t("pending") : submitText}</Button>
        </div>
      </form>
    </Modal>
  )
}
