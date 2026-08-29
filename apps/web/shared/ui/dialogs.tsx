"use client"

import type { FormEvent, ReactNode } from "react"
import { useEffect, useRef } from "react"
import { X } from "lucide-react"
import { useT } from "@/shared/i18n/context"
import { ICON_SIZE } from "./internals"
import styles from "./styles/primitives.module.css"
import { uiMessages } from "./i18n"
import { Button, Flex, Text } from "./primitives"

type ModalProps = {
  title?: string
  open: boolean
  children?: ReactNode
  content?: ReactNode
  width?: number
  onOpenChange?: (open: boolean) => void
}

export function Modal({ title, open, children, content, width, onOpenChange }: ModalProps) {
  const t = useT(uiMessages)
  const onOpenChangeRef = useRef(onOpenChange)
  const dialogRef = useRef<HTMLElement>(null)

  useEffect(() => { onOpenChangeRef.current = onOpenChange }, [onOpenChange])
  useEffect(() => {
    if (!open) return
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onOpenChangeRef.current?.(false)
    }
    document.addEventListener("keydown", handleKeyDown)
    return () => document.removeEventListener("keydown", handleKeyDown)
  }, [open])
  useEffect(() => {
    if (!open) return
    const node = dialogRef.current
    if (!node || node.contains(document.activeElement)) return
    const target = node.querySelector<HTMLElement>("[autofocus]") ?? node
    target.focus({ preventScroll: true })
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
        <div className={styles.modalBody}>{content ?? children}</div>
      </section>
    </div>
  )
}

type ConfirmProps = {
  open: boolean
  title?: string
  message?: string
  content?: string
  cancelText?: string
  confirmText?: string
  onCancel?: () => void
  onConfirm?: () => void
  onClose?: () => void
}

// 帶文字的 props 一律以 `??` 在函式內套用預設值，不寫在參數列上：參數預設值是模組
// 載入時就固定下來的，拿不到當下的語系。
export function Confirm({
  open,
  title,
  message,
  content,
  cancelText,
  confirmText,
  onCancel,
  onConfirm,
  onClose,
}: ConfirmProps) {
  const t = useT(uiMessages)
  return (
    <Modal title={title ?? t("confirmTitle")} open={open} onOpenChange={(next) => { if (!next) onClose?.() }}>
      <Flex direction="column" gap={4}>
        {(message || content) && <Text text={message ?? content} />}
        <Flex justify="flex-end" gap={2}>
          <Button variant="outlined" text={cancelText ?? t("cancel")} onClick={onCancel} />
          <Button text={confirmText ?? t("confirm")} onClick={onConfirm} />
        </Flex>
      </Flex>
    </Modal>
  )
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
      <form className={styles.dialogForm} onSubmit={onSubmit}>
        {children}
        <div className={styles.dialogFormActions}>
          <Button variant="outlined" text={t("cancel")} disabled={isPending} onClick={onClose} />
          <Button type="submit" text={isPending ? pendingText ?? t("pending") : submitText} disabled={isPending} />
        </div>
      </form>
    </Modal>
  )
}
