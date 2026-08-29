/**
 * 全站預設主題。主題檔在 `app/themes/`，每一份宣告一組 `--color-*`，由 `<html data-theme="…">`
 * 選擇；每一份都會載入，切換是 CSS 選擇器的事，不是「載哪個檔案」的事。
 *
 * **這是下游預期會改的一行。** 要加自訂主題：在 `app/themes/` 多放一份、把檔名加進
 * `ThemeName`、在**兩個進入點**（`app/layout.tsx` 與 `app/global-error.tsx`）各加一行 import，
 * 然後改 `DEFAULT_THEME`。
 *
 * 明暗不在這裡，因為**沒有明暗**：這個模板是單一深色色調，`color-scheme` 固定在
 * `app/tokens/semantic.css`。要第二種色調就是多一份主題，理由見 docs/design-system.md。
 */

/** 可用的主題，對應 `app/themes/<name>.css`。 */
export type ThemeName = "default"

export const DEFAULT_THEME: ThemeName = "default"
