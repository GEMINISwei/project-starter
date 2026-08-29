// UI kit 的內部工具；版面元件直接使用 `as`、`className` 與 `style`。

export function cls(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ")
}

/** 版面元件共用的基本 props：換 HTML 標籤、加 class、加行內樣式。 */
export type BaseProps = {
  /** 要渲染成哪個 HTML 標籤，預設由各元件決定。例：`<Container as="main">`。 */
  as?: React.ElementType
  className?: string
  style?: React.CSSProperties
}

/**
 * 間距刻度的階號。刻意是聯集而不是 `number`：階號不是倍率，而是 `tokens/semantic.css` 裡真的
 * 存在的那幾個 token。收成 `number` 的話 `gap={7}` 會產生不存在的 `var(--space-7)`，
 * gap 靜靜變成 0。
 */
export type SpaceStep = 1 | 2 | 3 | 4 | 5 | 6 | 8 | 10 | 12

/**
 * 間距：階號換成對應的 token，字串原樣輸出。
 *
 * 回傳 `var(--space-n)` 而不是自己算 px —— 刻度的單一事實來源留在 CSS 那一側
 * （`tokens/primitives.css` 的 `--ds-space-*`）。在這裡算 px 的話，改刻度要同時改兩邊。
 */
export function spacing(value: SpaceStep | string | undefined) {
  if (value === undefined) return undefined
  return typeof value === "number" ? `var(--space-${value})` : value
}

/**
 * 圖示尺寸。lucide 的 `size` prop 產生 `<svg width height>`，CSS 的 `--size-icon-*` 管不到它，
 * 所以刻度在這裡再宣告一份，**數字必須與 `--ds-size-icon-*` 相同**（由 `check-tokens.mjs` 比對）。
 *
 * 尺寸會隨斷點變的圖示（側欄與底部導覽）不要用這個 —— media query 改得動 CSS，改不動 prop。
 */
export const ICON_SIZE = { sm: 16, md: 20, lg: 24 } as const
