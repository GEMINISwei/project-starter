// 表單元件一律使用具名 props，避免同一個值有多個設定入口。
"use client"

import type * as React from "react"
import type { CSSProperties, HTMLInputTypeAttribute, ReactNode } from "react"
import { useId } from "react"
import { ChevronDown } from "lucide-react"
import { useT } from "@/shared/i18n/context"
import { cls, ICON_SIZE } from "./internals"
import styles from "./styles/primitives.module.css"
import { uiMessages } from "./i18n"

type TextInputProps = {
  id?: string
  name?: string
  label?: string
  value?: string | number
  defaultValue?: string | number
  type?: HTMLInputTypeAttribute
  required?: boolean
  disabled?: boolean
  multiline?: boolean
  rows?: number
  min?: number
  step?: number | string
  width?: string | number
  style?: CSSProperties
  inputMode?: React.HTMLAttributes<HTMLInputElement>["inputMode"]
  placeholder?: string
  autoComplete?: string
  autoFocus?: boolean
  error?: string
  /** 可見標籤在別處時用（例如登入頁只有 placeholder），此時不要再給 `label`。 */
  ariaLabel?: string
  /** 輸入框左側的圖示。給了之後左內距會讓出空間。 */
  icon?: ReactNode
  /** 輸入框右側的附加控制項（例如密碼顯示切換）。給了之後右內距會讓出空間。 */
  trailing?: ReactNode
  /** lg 給登入這類刻意放大的表單；預設 md。 */
  size?: "md" | "lg"
  onChange?: (value: string) => void
}

/**
 * 前置圖示與尾端控制項的版面。
 *
 * 抽出來是因為 `TextInput` 本身已經在處理 label／multiline／error 三個分支，
 * 再加上這裡的兩個會讓它超過複雜度上限 —— 而那個上限擋的正是「一個函式做太多事」。
 */
function AdornedInput({ icon, trailing, className, children }: {
  icon?: ReactNode
  trailing?: ReactNode
  className: string
  children: ReactNode
}) {
  if (!icon && !trailing) return children
  return (
    <span className={className}>
      {icon && <span className={styles.inputIcon}>{icon}</span>}
      {children}
      {trailing && <span className={styles.inputTrailing}>{trailing}</span>}
    </span>
  )
}

export function TextInput({
  id,
  name,
  label,
  multiline,
  rows = 3,
  width,
  style,
  error,
  ariaLabel,
  icon,
  trailing,
  size = "md",
  ...props
}: TextInputProps) {
  // id 一律由 useId 產生，**不要退回用 name**：同一頁出現兩個同名欄位時 name 會產生
  // 重複的 DOM id，`aria-describedby` 指到哪一個是未定義的。label 已經包住輸入框，
  // id 存在的唯一理由就是把錯誤訊息接上去。
  const generatedId = useId()
  const inputId = id ?? generatedId
  const errorId = error ? `${inputId}-error` : undefined
  const { onChange, ...inputProps } = props
  const accessibility = {
    id: inputId,
    name,
    "aria-label": ariaLabel,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": errorId,
  }

  return (
    <label className={styles.field} style={{ width }}>
      {label && (
        <span className={styles.label}>
          {label}
          {inputProps.required && <span style={{ color: "var(--color-danger-fg)", marginLeft: 2 }}>*</span>}
        </span>
      )}
      {multiline ? (
        <textarea
          className={styles.input}
          rows={rows}
          style={style}
          onChange={(event) => onChange?.(event.target.value)}
          {...accessibility}
          {...(inputProps as React.TextareaHTMLAttributes<HTMLTextAreaElement>)}
        />
      ) : (
        // 沒有圖示與尾端控制項時不多包一層 DOM，維持原本的單一 input。
        <AdornedInput icon={icon} trailing={trailing} className={styles.inputAdorned}>
          <input
            className={cls(
              styles.input,
              size === "lg" && styles.inputLg,
              icon ? styles.inputWithIcon : undefined,
              trailing ? styles.inputWithTrailing : undefined,
              error && styles.inputError,
            )}
            style={style}
            onChange={(event) => onChange?.(event.target.value)}
            {...accessibility}
            {...(inputProps as React.InputHTMLAttributes<HTMLInputElement>)}
          />
        </AdornedInput>
      )}
      {error && <span id={errorId} className={styles.fieldError} role="alert">{error}</span>}
    </label>
  )
}

/**
 * 啟用／停用的下拉選項。
 *
 * 是 hook 而不是常數陣列：label 要跟著語系走，而模組載入時還沒有語系。
 * 所有消費端都是 client component，所以 hook 這個形式沒有增加限制。
 */
export function useActiveStatusOptions() {
  const t = useT(uiMessages)

  return [
    { value: "active", label: t("statusActive") },
    { value: "disabled", label: t("statusDisabled") },
  ] as const
}

type SelectInputProps = {
  id?: string
  name?: string
  label?: string
  value?: string
  defaultValue?: string
  required?: boolean
  disabled?: boolean
  width?: string | number
  style?: CSSProperties
  options: ReadonlyArray<{ label?: string; text?: string; value: string }>
  autoFocus?: boolean
  error?: string
  /** 可見標籤在別處時用（例如設定頁的列名），此時不要再給 `label`。 */
  ariaLabel?: string
  onChange?: (value: string) => void
}

export function SelectInput({
  id, name, label, options, width, style, error, ariaLabel, ...props
}: SelectInputProps) {
  // id 的產生方式與 TextInput 一致，理由見那裡。
  const generatedId = useId()
  const inputId = id ?? generatedId
  const errorId = error ? `${inputId}-error` : undefined
  const { onChange, ...selectProps } = props
  return (
    <label className={styles.field} style={{ width }}>
      {label && (
        <span className={styles.label}>
          {label}
          {selectProps.required && <span style={{ color: "var(--color-danger-fg)", marginLeft: 2 }}>*</span>}
        </span>
      )}
      <span className={styles.selectControl}>
        <select
          className={styles.select}
          id={inputId}
          name={name}
          aria-label={ariaLabel}
          aria-invalid={error ? true : undefined}
          aria-describedby={errorId}
          style={style}
          onChange={(event) => onChange?.(event.target.value)}
          {...selectProps}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>{option.label ?? option.text}</option>
          ))}
        </select>
        <ChevronDown className={styles.selectIndicator} size={ICON_SIZE.sm} aria-hidden="true" />
      </span>
      {error && <span id={errorId} className={styles.fieldError} role="alert">{error}</span>}
    </label>
  )
}

type CheckboxInputProps = {
  name?: string
  label: string
  checked: boolean
  disabled?: boolean
  /** 選項下方的補充說明，例如「不勾選時不會產生邀請碼」。 */
  hint?: string
  onChange?: (checked: boolean) => void
}

/**
 * 布林值輸入，`onChange` 直接提供 boolean。
 */
export function CheckboxInput({
  name,
  label,
  checked,
  disabled,
  hint,
  onChange,
}: CheckboxInputProps) {
  return (
    <div>
      <label className={styles.checkboxField}>
        <input
          type="checkbox"
          className={styles.checkbox}
          name={name}
          checked={checked}
          disabled={disabled}
          onChange={(event) => onChange?.(event.target.checked)}
        />
        <span className={styles.checkboxLabel}>{label}</span>
      </label>
      {hint && <span className={styles.fieldHint}>{hint}</span>}
    </div>
  )
}

type NumberInputProps = {
  name?: string
  label?: string
  value: number
  min?: number
  max?: number
  step?: number
  required?: boolean
  disabled?: boolean
  width?: string | number
  hint?: string
  onChange?: (value: number) => void
}

/**
 * 數值輸入。`onChange` 直接給 `number`，並在元件內套用 min/max。
 */
export function NumberInput({
  name,
  label,
  value,
  min,
  max,
  step,
  required,
  disabled,
  width,
  hint,
  onChange,
}: NumberInputProps) {
  function handleChange(raw: string) {
    // 空字串與非數字都回落到 min（沒設就是 0），避免把 NaN 交給呼叫端。
    const parsed = Number(raw)
    const fallback = min ?? 0
    let next = raw.trim() === "" || Number.isNaN(parsed) ? fallback : parsed

    if (min !== undefined) next = Math.max(min, next)
    if (max !== undefined) next = Math.min(max, next)

    onChange?.(next)
  }

  return (
    <label className={styles.field} style={{ width }}>
      {label && (
        <span className={styles.label}>
          {label}
          {required && <span style={{ color: "var(--color-danger-fg)", marginLeft: 2 }}>*</span>}
        </span>
      )}
      <input
        type="number"
        className={styles.input}
        name={name}
        value={String(value)}
        min={min}
        max={max}
        step={step}
        required={required}
        disabled={disabled}
        onChange={(event) => handleChange(event.target.value)}
      />
      {hint && <span className={styles.fieldHint}>{hint}</span>}
    </label>
  )
}

type FormProps = {
  id?: string
  children: React.ReactNode
  onSubmit?: (event: React.FormEvent<HTMLFormElement>) => void
}

// 整頁表單的容器，欄位間距與 `FormDialog` 內部那個 form 一致。
// `id` 是給 `FormPageShell` 的送出鈕用 `form="<id>"` 從表單外部觸發的。
export function Form({ id, children, onSubmit }: FormProps) {
  return (
    <form id={id} className={styles.dialogForm} onSubmit={onSubmit}>
      {children}
    </form>
  )
}
