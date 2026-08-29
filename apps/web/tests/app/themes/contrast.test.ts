// @vitest-environment node

import { readdirSync, readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

/**
 * 每一份主題的對比度門檻。
 *
 * **不是只測 `default`**：`app/themes/` 底下每多一份主題，這裡就多跑一輪同一組門檻。
 * 導入外部 DS 時新主題通常就是 `DEFAULT_THEME`（使用者實際看到的那一份），
 * 而上游的色票是照它自己的畫面挑的，深色底上的對比沒有人保證過 —— 那正是這份測試要接住的。
 *
 * 檢查器管不到這一層：`check-tokens.mjs` 認的是 token 的**結構**（誰引用誰、有沒有宣告），
 * 對比度要把 `var()` 與 `color-mix()` 一路解析成實際色值才算得出來。
 */

type Color = { red: number; green: number; blue: number; alpha: number }

const TOKEN_DIR = "app/tokens"
const THEME_DIR = "app/themes"

/** 收集一份 CSS 裡所有 `--x: value;` 宣告。 */
function declarationsIn(file: string, into: Map<string, string>) {
  const source = readFileSync(path.resolve(file), "utf8")
  for (const match of source.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    into.set(match[1], match[2].trim())
  }
}

/**
 * 原始層與語意層的所有宣告，**含 `vendor/`**。
 *
 * 掃目錄而不是列檔名：導入 DS 之後 `primitives.css` 的值會變成 `var(--<上游的名字>)`，
 * 而那個名字宣告在 `app/tokens/vendor/<ds>/` —— 漏掉那一層，解析會直接停在「找不到」。
 */
function baseDeclarations() {
  const base = new Map<string, string>()
  const entries = readdirSync(TOKEN_DIR, { recursive: true, withFileTypes: true })
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith(".css")) continue
    declarationsIn(path.join(entry.parentPath, entry.name), base)
  }
  return base
}

const themeFiles = readdirSync(THEME_DIR).filter((name) => name.endsWith(".css"))

// 掃不到主題檔時「沒有主題」與「全部通過」的輸出一模一樣。寧可誤報也不要安靜綠燈
// （同 check-tokens.mjs 的空集合守衛）。
it("掃得到主題檔", () => {
  expect(themeFiles.length).toBeGreaterThan(0)
})

function parseHex(value: string): Color | undefined {
  const match = value.match(/^#([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i)
  if (!match) return undefined
  return {
    red: Number.parseInt(match[1], 16),
    green: Number.parseInt(match[2], 16),
    blue: Number.parseInt(match[3], 16),
    alpha: 1,
  }
}

function mix(first: Color, weight: number, second: Color): Color {
  const alpha = first.alpha * weight + second.alpha * (1 - weight)
  const channel = (firstValue: number, secondValue: number) => (
    (firstValue * first.alpha * weight + secondValue * second.alpha * (1 - weight)) / alpha
  )
  return {
    red: channel(first.red, second.red),
    green: channel(first.green, second.green),
    blue: channel(first.blue, second.blue),
    alpha,
  }
}

/** 把一個 token 解析成實際色值：`var()` 一路跟下去，`color-mix()` 自己算。 */
function resolver(declarations: Map<string, string>) {
  const resolve = (token: string): Color => {
    const value = declarations.get(token)
    if (!value) throw new Error(`找不到 ${token}`)

    const hex = parseHex(value)
    if (hex) return hex

    const reference = value.match(/^var\((--[\w-]+)\)$/)
    if (reference) return resolve(reference[1])

    const colorMix = value.match(
      /^color-mix\(\s*in srgb,\s*var\((--[\w-]+)\)\s+(\d+)%,\s*(?:var\((--[\w-]+)\)|(transparent))\)$/,
    )
    if (!colorMix) throw new Error(`無法解析 ${token}: ${value}`)
    const second = colorMix[3]
      ? resolve(colorMix[3])
      : { red: 0, green: 0, blue: 0, alpha: 0 }
    return mix(resolve(colorMix[1]), Number(colorMix[2]) / 100, second)
  }
  return resolve
}

function composite(foreground: Color, background: Color): Color {
  return mix(
    { ...foreground, alpha: 1 },
    foreground.alpha,
    { ...background, alpha: 1 },
  )
}

function luminance(color: Color) {
  const linear = (channel: number) => {
    const normalized = channel / 255
    return normalized <= 0.04045
      ? normalized / 12.92
      : ((normalized + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * linear(color.red)
    + 0.7152 * linear(color.green)
    + 0.0722 * linear(color.blue)
}

function contrast(first: Color, second: Color) {
  const lighter = Math.max(luminance(first), luminance(second))
  const darker = Math.min(luminance(first), luminance(second))
  return (lighter + 0.05) / (darker + 0.05)
}

/**
 * 文字實際會疊在哪些底上。
 *
 * **一種文字對一種表面測一次，不是只測最常見的那一組。** 深色底上表面愈亮對比愈緊，
 * 所以同一種文字在不同表面上的差距可以跨過門檻：muted 對 `surface-card` 是 4.57:1（過），
 * 疊在 `surface-raised` 上就是 4.17:1（不過），而 `modules/push` 的推播提示正是後者。
 * 四種表面都要問一次。
 */
const TEXT_ON_SURFACE: ReadonlyArray<[text: string, surface: string]> = [
  ["--color-text-body", "--color-bg-app"],
  ["--color-text-secondary", "--color-bg-app"],
  ["--color-text-heading", "--color-bg-app"],
  ["--color-text-muted", "--color-bg-app"],
  ["--color-text-muted", "--color-surface-card"],
  ["--color-text-muted", "--color-surface-raised"],
  ["--color-text-muted", "--color-surface-hover"],
]

describe.each(themeFiles)("%s 的對比", (themeFile) => {
  const declarations = baseDeclarations()
  declarationsIn(path.join(THEME_DIR, themeFile), declarations)
  const resolve = resolver(declarations)

  it("主要行動的 normal 與 hover 文字都至少 4.5:1", () => {
    const text = resolve("--color-text-on-primary")
    expect(contrast(text, resolve("--color-action-primary"))).toBeGreaterThanOrEqual(4.5)
    expect(contrast(text, resolve("--color-action-primary-hover"))).toBeGreaterThanOrEqual(4.5)
  })

  it.each(TEXT_ON_SURFACE)("%s 在 %s 上至少 4.5:1", (text, surface) => {
    expect(contrast(resolve(text), resolve(surface))).toBeGreaterThanOrEqual(4.5)
  })

  it("控制項邊界與 focus ring 在卡片上至少 3:1", () => {
    const card = resolve("--color-surface-card")
    const focus = composite(resolve("--color-focus-ring"), card)
    expect(contrast(resolve("--color-border-control"), card)).toBeGreaterThanOrEqual(3)
    expect(contrast(focus, card)).toBeGreaterThanOrEqual(3)
  })
})
