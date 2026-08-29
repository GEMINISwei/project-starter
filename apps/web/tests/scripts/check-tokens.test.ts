import { mkdtempSync, mkdirSync, writeFileSync, rmSync, readFileSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { afterEach, describe, expect, it } from "vitest"
import { collectTokenErrors } from "../../scripts/check-tokens.mjs"

/**
 * 檢查器自己的測試。
 *
 * 用 fixture 而不是掃真的 repo：真 repo 全綠時，「規則根本沒接上」與「規則通過」
 * 產生一模一樣的輸出。每條規則都要有一個**確定會被擋**的樣本，才證明它活著 ——
 * 同 `tests/app/route-adapters.test.ts` 用 canary 防止 glob 壞掉而空過的理由。
 */

const roots: string[] = []

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

/** 建一棵最小的 app 樹；`files` 的 key 是相對路徑。 */
function fixture(files: Record<string, string>) {
  const root = mkdtempSync(path.join(tmpdir(), "check-tokens-"))
  roots.push(root)
  for (const [relative, content] of Object.entries(files)) {
    const full = path.join(root, relative)
    mkdirSync(path.dirname(full), { recursive: true })
    writeFileSync(full, content)
  }
  return root
}

/**
 * 每個 fixture 都要有的最小 token 定義檔，讓「沒被測到的規則」不會誤報。
 *
 * 放 `app/tokens/` 而不是 `app/globals.css`：只有 `app/tokens/**` 與 `app/themes/**`
 * 是 token 定義檔。`globals.css` 不算：它不宣告 token，給它那個身分只是白送
 * 「可寫裸色值」與「可用 `--ds-*`」的豁免（見下方規則 c 的第三個 case）。
 */
const TOKENS = `:root {\n  --color-text-body: #374151;\n}\n`
const USES_TOKEN = `.a { color: var(--color-text-body); }\n`
const USES_CLASS = `import s from "./x.module.css"\nexport const A = () => <p className={s.a} />\n`

describe("規則 a：var() 引用的 token 必須有人宣告", () => {
  it("引用沒有宣告過的 token 會被擋", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `${USES_TOKEN}.b { border-color: var(--color-nope); }\n`,
      "modules/x/ui/X.tsx": `${USES_CLASS}export const B = () => <p className={s.b} />\n`,
    })
    expect(collectTokenErrors(root)).toContainEqual(
      expect.stringContaining("--color-nope"),
    )
  })

  it("有 fallback 也一樣要擋 —— fallback 只是把錯誤藏起來", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `.a { color: var(--color-text-body, var(--color-nope)); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("--color-nope"))
  })

  it("同一份 CSS 裡宣告的元件級 token 不算幽靈", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      // 值走 token：這一條測的是規則 a，裸 px 會踩到規則 i 的自訂屬性那一半。
      "modules/x/ui/x.module.css":
        `.a { --gap: var(--color-text-body); gap: 0; color: var(--gap); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("由 TSX 以行內樣式設定的 token 不算幽靈", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "shared/ui/styles/p.module.css": `.a { gap: var(--flex-gap, 0); color: var(--color-text-body); }\n`,
      "shared/ui/p.tsx": `import s from "./styles/p.module.css"\n`
        + `export const P = () => <div className={s.a} style={{ "--flex-gap": "8px" }} />\n`,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("TSX 行內樣式裡的幽靈 token 也要擋", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "app/e.tsx": `export const E = () => <p style={{ color: "var(--fs-nope)" }} />\n`,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("--fs-nope"))
  })
})

describe("以樣板字串組出來的 token", () => {
  it("整個家族都算有人用 —— 靜態上看不出組出來的是哪一階", () => {
    const root = fixture({
      "app/tokens/base.css": `:root {\n  --space-2: 8px;\n  --space-4: 16px;\n}\n`,
      "shared/ui/internals.ts": "export const gap = (n: number) => `var(--space-${n})`\n",
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("被截斷的前綴本身不會被當成幽靈 token", () => {
    const root = fixture({
      "app/tokens/base.css": `:root {\n  --space-2: 8px;\n}\n`,
      "shared/ui/internals.ts": "export const gap = (n: number) => `var(--space-${n})`\n",
    })
    expect(collectTokenErrors(root)).not.toContainEqual(expect.stringContaining("引用了沒有宣告過"))
  })
})

describe("規則 b：宣告了沒人用的 token", () => {
  it("沒人引用的 token 會被擋", () => {
    const root = fixture({
      "app/tokens/base.css": `${TOKENS.trimEnd().slice(0, -1)}  --color-unused: #fff;\n}\n`,
      "modules/x/ui/x.module.css": USES_TOKEN,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("--color-unused"))
  })
})

describe("規則 c：token 定義檔以外不可出現裸色值", () => {
  it("module CSS 裡的 hex 會被擋", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `${USES_TOKEN}.b { background: #ffffff; }\n`,
      "modules/x/ui/X.tsx": `${USES_CLASS}export const B = () => <p className={s.b} />\n`,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("#ffffff"))
  })

  it("module CSS 裡的 rgba() 會被擋", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `${USES_TOKEN}.b { background: rgba(0, 0, 0, 0.5); }\n`,
      "modules/x/ui/X.tsx": `${USES_CLASS}export const B = () => <p className={s.b} />\n`,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("rgba("))
  })

  it("token 定義檔裡的裸色值是正常的", () => {
    const root = fixture({
      "app/tokens/base.css": `:root {\n  --color-text-body: rgba(17, 24, 39, 0.9);\n}\n`,
      "modules/x/ui/x.module.css": USES_TOKEN,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("oklch() 也要擋 —— 現在的 DS 產出多半用它，那正是原始值繞過對照表的縫隙", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `${USES_TOKEN}.b { color: oklch(0.7 0.1 250); }\n`,
      "modules/x/ui/X.tsx": `${USES_CLASS}export const B = () => <p className={s.b} />\n`,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("oklch("))
  })

  it("globals.css 不是 token 定義檔 —— 它不宣告 token，不該拿到裸色值的豁免", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "app/globals.css": `body { color: #ffffff; }\n`,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("#ffffff"))
  })
})

describe("規則 d：模組與組裝層只能引用語意層", () => {
  it("模組直接引用原始層會被擋", () => {
    const root = fixture({
      "app/tokens/base.css": `:root {\n  --ds-gray-900: #111;\n  --color-text-body: var(--ds-gray-900);\n}\n`,
      "modules/x/ui/x.module.css": `.a { color: var(--ds-gray-900); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("--ds-gray-900"))
  })
})

describe("規則 e：composes 不可跨出 UI kit", () => {
  it("模組 composes 進 shared/ui/styles 會被擋", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "shared/ui/styles/p.module.css": `.card { color: var(--color-text-body); }\n`,
      "shared/ui/p.tsx": `import s from "./styles/p.module.css"\nexport const P = () => <i className={s.card} />\n`,
      "modules/x/ui/x.module.css": `.a { composes: card from "../../../shared/ui/styles/p.module.css"; }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("composes"))
  })

  it("UI kit 內部彼此 composes 是允許的", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "shared/ui/styles/p.module.css": `.card { color: var(--color-text-body); }\n`,
      "shared/ui/styles/t.module.css": `.row { composes: card from "./p.module.css"; }\n`,
      "shared/ui/p.tsx": `import s from "./styles/t.module.css"\nexport const P = () => <i className={s.row} />\n`,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })
})

describe("規則 f：沒有任何 TSX 引用的 class 是死碼", () => {
  it("沒人用的 class 會被擋", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `${USES_TOKEN}.dead { color: var(--color-text-body); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("dead"))
  })

  it("只被 composes 取用的 class 不算死碼", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "shared/ui/styles/p.module.css": `.card { color: var(--color-text-body); }\n`,
      "shared/ui/styles/t.module.css": `.row { composes: card from "./p.module.css"; }\n`,
      "shared/ui/p.tsx": `import s from "./styles/t.module.css"\nexport const P = () => <i className={s.row} />\n`,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("非 module 的全域 CSS 不受這條管", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "shared/ui/styles/message-page.css": `.messagePage { color: var(--color-text-body); }\n`,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })
})

describe("規則 h：TSX 的 styles.x 必須真的存在於 CSS", () => {
  it("型別承諾了但 CSS 沒實作的 variant 會被擋", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "shared/ui/styles/p.module.css": `.a { color: var(--color-text-body); }\n`,
      "shared/ui/p.tsx": `import s from "./styles/p.module.css"\n`
        + `const MAP = { a: s.a, b: s.missingOne }\n`
        + `export const P = () => <i className={MAP.a} />\n`,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("missingOne"))
  })

  it("import 路徑裡長得像成員存取的片段不算引用", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "shared/ui/styles/table.module.css": `.row { color: var(--color-text-body); }\n`,
      "shared/ui/t.tsx": `import table from "./styles/table.module.css"\n`
        + `export const T = () => <i className={table.row} />\n`,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it(":where() 裡宣告的 class 算存在", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "shared/ui/styles/p.module.css": `:where(.flex) { color: var(--color-text-body); }\n`,
      "shared/ui/p.tsx": `import s from "./styles/p.module.css"\n`
        + `export const P = () => <i className={s.flex} />\n`,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })
})

describe("規則 g：斷點必須在允許清單內", () => {
  it("清單外的斷點會被擋", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `${USES_TOKEN}@media (max-width: 617px) { .a { color: var(--color-text-body); } }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("617px"))
  })

  it("清單內的斷點是允許的", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `${USES_TOKEN}@media (max-width: 720px) { .a { color: var(--color-text-body); } }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })
})

describe("規則 i：節奏類屬性不可寫死 px", () => {
  it("寫死的 padding 會被擋", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `.a { padding: 13px; color: var(--color-text-body); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("13px"))
  })

  it("3px 以下是光學微調，放行", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `.a { margin-top: 1px; color: var(--color-text-body); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("負值也算 —— 取絕對值判斷", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `.a { margin: -32px; color: var(--color-text-body); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("-32px"))
  })

  it("元件自己的尺寸（width／height）不受這條管", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `.a { width: 40px; height: 104px; color: var(--color-text-body); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("media query 的斷點由規則 g 管，不重複擋", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `${USES_TOKEN}@media (max-width: 720px) { .a { color: var(--color-text-body); } }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })
})

describe("規則 i：尺寸屬性的算式裡藏的間距", () => {
  it("跟視窗尺寸做加減的那一項是留白，要擋", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `.a { width: calc(100vw - 13px); color: var(--color-text-body); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("13px"))
  })

  it("單獨當上界的 px 是元件尺寸，放行", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `.a { width: min(100%, 560px); color: var(--color-text-body); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("與 env(safe-area-*) 並列的下限也是留白，要擋", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css":
        `.a { max-height: calc(100dvh - max(16px, env(safe-area-inset-top))); color: var(--color-text-body); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("16px"))
  })

  it("單純的元件寬高不受影響", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `.a { width: 40px; min-height: 104px; color: var(--color-text-body); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })
})

describe("規則 j：var() 不能用前置負號取負", () => {
  it("-var(…) 會被擋 —— 那是無效 CSS，整條宣告會被安靜丟掉", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `.a { margin: -var(--space-8); color: var(--color-text-body); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("calc(var(…) * -1)"))
  })

  it("calc(var(…) * -1) 是正確寫法，放行", () => {
    const root = fixture({
      "app/tokens/base.css": `:root {\n  --space-8: 32px;\n  --color-text-body: #374151;\n}\n`,
      "modules/x/ui/x.module.css": `.a { margin: calc(var(--space-8) * -1); color: var(--color-text-body); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })
})

describe("規則 k：語意層必須由 --ds-* 撐著", () => {
  it("語意層自己帶值會被擋", () => {
    const root = fixture({
      "app/tokens/primitives.css": `:root {\n  --ds-space-3: 12px;\n}\n`,
      "app/tokens/semantic.css": `:root {\n  --gap-card: 12px;\n}\n`,
      "modules/x/ui/x.module.css": `.a { gap: var(--gap-card); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("--gap-card"))
  })

  it("轉指到 --ds-* 就放行", () => {
    const root = fixture({
      "app/tokens/primitives.css": `:root {\n  --ds-space-3: 12px;\n}\n`,
      "app/tokens/semantic.css": `:root {\n  --gap-card: var(--ds-space-3);\n}\n`,
      "modules/x/ui/x.module.css": `.a { gap: var(--gap-card); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("多行宣告也要檢查 —— 只看單行會整條漏掉", () => {
    const root = fixture({
      "app/tokens/primitives.css": `:root {\n  --ds-gray-900: #111827;\n}\n`,
      "app/themes/default.css":
        `:root {\n  --color-scrim: light-dark(\n    rgba(17, 24, 39, 0.38),\n    rgba(0, 0, 0, 0.7));\n}\n`,
      "modules/x/ui/x.module.css": `.a { background: var(--color-scrim); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("--color-scrim"))
  })

  it("allowlist 內的刻意例外放行（疊層順序不是 DS 給的）", () => {
    const root = fixture({
      "app/tokens/primitives.css": `:root {\n  --ds-space-3: 12px;\n}\n`,
      "app/tokens/semantic.css": `:root {\n  --z-overlay: 1000;\n  --gap-card: var(--ds-space-3);\n}\n`,
      "modules/x/ui/x.module.css": `.a { z-index: var(--z-overlay); gap: var(--gap-card); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })
})

describe("規則 l：focus 外環不可自己組", () => {
  it("自己組 0 0 0 3px 會被擋", () => {
    const root = fixture({
      "app/tokens/base.css": `:root {\n  --color-focus-ring: rgba(0,0,0,.3);\n  --focus-ring: 0 0 0 3px var(--color-focus-ring);\n}\n`,
      "modules/x/ui/x.module.css": `.a:focus { box-shadow: 0 0 0 3px var(--color-focus-ring); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("var(--focus-ring)"))
  })

  it("用 var(--focus-ring) 放行", () => {
    const root = fixture({
      "app/tokens/base.css": `:root {\n  --color-focus-ring: rgba(0,0,0,.3);\n  --focus-ring: 0 0 0 3px var(--color-focus-ring);\n}\n`,
      "modules/x/ui/x.module.css": `.a:focus { box-shadow: var(--focus-ring); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })
})

describe("規則 m：JS 與 CSS 各一份的數字必須相等", () => {
  const ICON_CSS = `:root {\n  --ds-size-icon-1: 16px;\n  --ds-size-icon-2: 20px;\n  --ds-size-icon-3: 24px;\n}\n`

  it("兩邊對不上會被擋", () => {
    const root = fixture({
      "app/tokens/primitives.css": ICON_CSS,
      "shared/ui/internals.ts": "export const ICON_SIZE = { sm: 16, md: 21, lg: 24 } as const\n",
      "modules/x/ui/x.module.css": `.a { width: var(--ds-size-icon-1); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("ICON_SIZE"))
  })

  it("對得上就放行", () => {
    const root = fixture({
      "app/tokens/primitives.css": ICON_CSS,
      "app/tokens/semantic.css": `:root {\n  --size-icon-sm: var(--ds-size-icon-1);\n}\n`,
      "shared/ui/internals.ts": "export const ICON_SIZE = { sm: 16, md: 20, lg: 24 } as const\n",
      "modules/x/ui/x.module.css": `.a { width: var(--size-icon-sm); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).not.toContainEqual(expect.stringContaining("ICON_SIZE"))
  })

  it("TS 那側整個不存在時跳過 —— 那棵樹沒有 UI kit", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": USES_TOKEN,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })
})

describe("vendor 層：外部 Design System 產出的落地處", () => {
  /** DS 原生的命名 —— 前綴由對方的專案決定，不會是 `--ds-*`。 */
  const VENDOR = `:root {\n  --grape-500: #7B5FE0;\n}\n`
  const ADAPTER = `:root {\n  --ds-brand: var(--grape-500);\n}\n`
  const SEMANTIC = `:root {\n  --color-primary: var(--ds-brand);\n}\n`
  const USES_PRIMARY = `.a { color: var(--color-primary); }\n`

  it("vendor 檔是 token 定義檔，裸色值放行", () => {
    const root = fixture({
      "app/tokens/vendor/grape/colors.css": VENDOR,
      "app/tokens/primitives.css": ADAPTER,
      "app/tokens/semantic.css": SEMANTIC,
      "modules/x/ui/x.module.css": USES_PRIMARY,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("規則 b 對 vendor 檔豁免 —— 上游給的色票本來就會有用不到的階", () => {
    const root = fixture({
      "app/tokens/vendor/grape/colors.css": `:root {\n  --grape-500: #7B5FE0;\n  --grape-100: #EDE6FB;\n}\n`,
      "app/tokens/primitives.css": ADAPTER,
      "app/tokens/semantic.css": SEMANTIC,
      "modules/x/ui/x.module.css": USES_PRIMARY,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("規則 n：vendor 的名字只能在 primitives.css 對照，模組直接用會被擋", () => {
    const root = fixture({
      "app/tokens/vendor/grape/colors.css": VENDOR,
      "app/tokens/primitives.css": ADAPTER,
      "app/tokens/semantic.css": SEMANTIC,
      "modules/x/ui/x.module.css": `${USES_PRIMARY}.b { border-color: var(--grape-500); }\n`,
      "modules/x/ui/X.tsx": `${USES_CLASS}export const B = () => <p className={s.b} />\n`,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("--grape-500"))
  })

  it("規則 n：vendor 檔內部互相引用放行 —— 那是上游自己的分層", () => {
    const root = fixture({
      "app/tokens/vendor/grape/colors.css": `:root {\n  --grape-500: #7B5FE0;\n  --brand: var(--grape-500);\n}\n`,
      "app/tokens/primitives.css": `:root {\n  --ds-brand: var(--brand);\n}\n`,
      "app/tokens/semantic.css": SEMANTIC,
      "modules/x/ui/x.module.css": USES_PRIMARY,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("規則 o：vendor 宣告了語意層已有的名字會被擋 —— 後載入者勝而且沒有紅燈", () => {
    const root = fixture({
      "app/tokens/vendor/grape/colors.css": `:root {\n  --grape-500: #7B5FE0;\n  --color-primary: #7B5FE0;\n}\n`,
      "app/tokens/primitives.css": ADAPTER,
      "app/tokens/semantic.css": SEMANTIC,
      "modules/x/ui/x.module.css": USES_PRIMARY,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("撞名"))
  })

  it("撞名時只報規則 o 那一行 —— 規則 n 不對每個合法呼叫點各報一次", () => {
    const root = fixture({
      "app/tokens/vendor/grape/colors.css": `:root {\n  --grape-500: #7B5FE0;\n  --color-primary: #7B5FE0;\n}\n`,
      "app/tokens/primitives.css": ADAPTER,
      "app/tokens/semantic.css": SEMANTIC,
      "modules/x/ui/x.module.css": USES_PRIMARY,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toHaveLength(1)
  })

  it("規則 o 只管 vendor —— 每份主題各宣告一次同一組 --color-* 是刻意的", () => {
    const root = fixture({
      "app/tokens/primitives.css": `:root {\n  --ds-gray-900: #111827;\n  --ds-white: #FFFFFF;\n}\n`,
      "app/themes/default.css":
        `:root {\n  --color-text-body: light-dark(var(--ds-gray-900), var(--ds-white));\n}\n`,
      "app/themes/warm.css":
        `:root[data-theme="warm"] {\n  --color-text-body: light-dark(var(--ds-gray-900), var(--ds-white));\n}\n`,
      "modules/x/ui/x.module.css": USES_TOKEN,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })
})

describe("規則 p：CSS 不可用 @import 拉外部資源", () => {
  it("Google Fonts 的 @import 會被擋 —— 字型走 next/font 是刻意的決定", () => {
    const root = fixture({
      "app/tokens/base.css": `@import url("https://fonts.googleapis.com/css2?family=Inter");\n${TOKENS}`,
      "modules/x/ui/x.module.css": USES_TOKEN,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("@import"))
  })

  it("放進 vendor 目錄也一樣擋 —— DS 的字型產出正是長這樣", () => {
    const root = fixture({
      "app/tokens/vendor/grape/fonts.css": `@import url("https://fonts.googleapis.com/css2?family=Fraunces");\n`,
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": USES_TOKEN,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("@import"))
  })
})

describe("規則 q：主題的三份清單必須一致", () => {
  const THEME_CSS = `:root {\n  --color-text-body: light-dark(var(--ds-gray-900), var(--ds-white));\n}\n`
  const PRIMITIVES = `:root {\n  --ds-gray-900: #111827;\n  --ds-white: #FFFFFF;\n}\n`

  /** 三份清單齊全的一棵樹；`themes` 決定要放哪幾份主題檔與 import。 */
  function themeTree(names: string[], declared: string[], imported: string[]) {
    const files: Record<string, string> = {
      "app/tokens/primitives.css": PRIMITIVES,
      "config/theme.ts": `export type ThemeName = ${declared.map((n) => `"${n}"`).join(" | ")}\n`
        + `export const DEFAULT_THEME: ThemeName = "${declared[0]}"\n`,
      "app/layout.tsx": `import "./tokens/primitives.css"\n`
        + imported.map((n) => `import "./themes/${n}.css"\n`).join(""),
      "modules/x/ui/x.module.css": USES_TOKEN,
      "modules/x/ui/X.tsx": USES_CLASS,
    }
    for (const name of names) files[`app/themes/${name}.css`] = THEME_CSS
    return fixture(files)
  }

  it("三份一致就放行", () => {
    expect(collectTokenErrors(themeTree(["default"], ["default"], ["default"]))).toEqual([])
  })

  it("ThemeName 有、但主題檔被刪掉了 —— data-theme 會靜靜沒作用", () => {
    const root = themeTree(["default"], ["default", "warm"], ["default"])
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("主題"))
  })

  it("主題檔在、但 layout.tsx 忘了 import", () => {
    const root = themeTree(["default", "warm"], ["default", "warm"], ["default"])
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("主題"))
  })

  it("被註解掉的 import 不算登記", () => {
    const root = fixture({
      "app/tokens/primitives.css": PRIMITIVES,
      "app/themes/default.css": THEME_CSS,
      "app/themes/warm.css": THEME_CSS,
      "config/theme.ts": `export type ThemeName = "default" | "warm"\n`,
      "app/layout.tsx": `import "./tokens/primitives.css"\n`
        + `import "./themes/default.css"\n// import "./themes/warm.css"\n`,
      "modules/x/ui/x.module.css": USES_TOKEN,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("主題"))
  })

  it("主題檔在、layout 也接了，但 global-error.tsx 少一份", () => {
    const root = fixture({
      "app/tokens/primitives.css": PRIMITIVES,
      "app/themes/default.css": THEME_CSS,
      "app/themes/warm.css": THEME_CSS,
      "config/theme.ts": `export type ThemeName = "default" | "warm"\n`,
      "app/layout.tsx": `import "./tokens/primitives.css"\n`
        + `import "./themes/default.css"\nimport "./themes/warm.css"\n`,
      "app/global-error.tsx": `import "./tokens/primitives.css"\n`
        + `import "./themes/default.css"\n`,
      "modules/x/ui/x.module.css": USES_TOKEN,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("app/global-error.tsx"))
  })

  it("沒有 config/theme.ts 的樹整條跳過 —— 那是還沒有組裝層的 fixture", () => {
    const root = fixture({
      "app/tokens/primitives.css": PRIMITIVES,
      "app/themes/default.css": THEME_CSS,
      "modules/x/ui/x.module.css": USES_TOKEN,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })
})

describe("規則 s：app/tokens 下的每份 CSS 都要被 layout.tsx 載入", () => {
  const VENDOR = `:root {\n  --grape-500: #7B5FE0;\n}\n`
  const ADAPTER = `:root {\n  --ds-brand: var(--grape-500);\n}\n`
  const SEMANTIC = `:root {\n  --color-primary: var(--ds-brand);\n}\n`
  const USES_PRIMARY = `.a { color: var(--color-primary); }\n`

  /** 導入一套 DS 之後的最小樹；`imported` 決定 layout.tsx 實際接了哪幾份。 */
  function vendorTree(imported: string[]) {
    return fixture({
      "app/tokens/vendor/grape/colors.css": VENDOR,
      "app/tokens/primitives.css": ADAPTER,
      "app/tokens/semantic.css": SEMANTIC,
      "app/layout.tsx": imported.map((rel) => `import "./tokens/${rel}"\n`).join(""),
      "modules/x/ui/x.module.css": USES_PRIMARY,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
  }

  const ALL = ["primitives.css", "semantic.css", "vendor/grape/colors.css"]

  it("每一份都接上就放行", () => {
    expect(collectTokenErrors(vendorTree(ALL))).toEqual([])
  })

  it("vendor 檔沒接上 —— 其他規則全綠，但那組顏色在瀏覽器裡會整批解不出來", () => {
    const root = vendorTree(["primitives.css", "semantic.css"])
    expect(collectTokenErrors(root)).toContainEqual(
      expect.stringContaining("app/tokens/vendor/grape/colors.css"),
    )
  })

  it("被註解掉的 import 不算接上", () => {
    const root = fixture({
      "app/tokens/primitives.css": ADAPTER,
      "app/tokens/semantic.css": SEMANTIC,
      "app/tokens/vendor/grape/colors.css": VENDOR,
      "app/layout.tsx": `import "./tokens/primitives.css"\n`
        + `import "./tokens/semantic.css"\n`
        + `// import "./tokens/vendor/grape/colors.css"\n`,
      "modules/x/ui/x.module.css": USES_PRIMARY,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("vendor/grape/colors.css"))
  })

  it("global-error.tsx 也要接上 —— 它取代 root layout，layout 的 import 不在它的文件裡", () => {
    const root = fixture({
      "app/tokens/primitives.css": ADAPTER,
      "app/tokens/semantic.css": SEMANTIC,
      "app/tokens/vendor/grape/colors.css": VENDOR,
      "app/layout.tsx": ALL.map((rel) => `import "./tokens/${rel}"\n`).join(""),
      "app/global-error.tsx": `import "./tokens/primitives.css"\nimport "./tokens/semantic.css"\n`,
      "modules/x/ui/x.module.css": USES_PRIMARY,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(
      expect.stringContaining("app/global-error.tsx"),
    )
  })

  it("兩個進入點都接齊就放行", () => {
    const imports = ALL.map((rel) => `import "./tokens/${rel}"\n`).join("")
    const root = fixture({
      "app/tokens/primitives.css": ADAPTER,
      "app/tokens/semantic.css": SEMANTIC,
      "app/tokens/vendor/grape/colors.css": VENDOR,
      "app/layout.tsx": imports,
      "app/global-error.tsx": imports,
      "modules/x/ui/x.module.css": USES_PRIMARY,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("沒有 app/layout.tsx 的樹整條跳過 —— 那是還沒有組裝層的 fixture", () => {
    const root = fixture({
      "app/tokens/primitives.css": ADAPTER,
      "app/tokens/semantic.css": SEMANTIC,
      "app/tokens/vendor/grape/colors.css": VENDOR,
      "modules/x/ui/x.module.css": USES_PRIMARY,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })
})

describe("規則 o：兩套 DS 之間也不可撞名", () => {
  it("兩個 vendor 目錄宣告同一個名字會被擋 —— 同樣是後載入者勝", () => {
    const root = fixture({
      "app/tokens/vendor/grape/spacing.css": `:root {\n  --space-md: 16px;\n}\n`,
      "app/tokens/vendor/cocoa/spacing.css": `:root {\n  --space-md: 12px;\n}\n`,
      "app/tokens/primitives.css": `:root {\n  --ds-space-4: var(--space-md);\n}\n`,
      "app/tokens/semantic.css": `:root {\n  --space-4: var(--ds-space-4);\n}\n`,
      "modules/x/ui/x.module.css": `.a { gap: var(--space-4); }\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("撞名"))
  })
})

describe("規則 r：每份主題必須宣告同一組 --color-*", () => {
  const PRIMITIVES = `:root {\n  --ds-gray-900: #111827;\n  --ds-white: #FFFFFF;\n}\n`
  const PAIR = "light-dark(var(--ds-gray-900), var(--ds-white))"

  it("某份主題少一個顏色會被擋 —— 它會靜靜沿用 default 的值", () => {
    const root = fixture({
      "app/tokens/primitives.css": PRIMITIVES,
      "app/themes/default.css":
        `:root {\n  --color-text-body: ${PAIR};\n  --color-bg-app: ${PAIR};\n}\n`,
      "app/themes/warm.css": `:root[data-theme="warm"] {\n  --color-text-body: ${PAIR};\n}\n`,
      "modules/x/ui/x.module.css": `${USES_TOKEN}.b { background: var(--color-bg-app); }\n`,
      "modules/x/ui/X.tsx": `${USES_CLASS}export const B = () => <p className={s.b} />\n`,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("--color-bg-app"))
  })

  it("兩份都完整就放行 —— 挑哪一階是各主題自己的事", () => {
    const root = fixture({
      "app/tokens/primitives.css": PRIMITIVES,
      "app/themes/default.css": `:root {\n  --color-text-body: ${PAIR};\n}\n`,
      "app/themes/warm.css":
        `:root[data-theme="warm"] {\n`
        + `  --color-text-body: light-dark(var(--ds-white), var(--ds-gray-900));\n}\n`,
      "modules/x/ui/x.module.css": USES_TOKEN,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("只有一份主題時不比對", () => {
    const root = fixture({
      "app/tokens/primitives.css": PRIMITIVES,
      "app/themes/default.css": `:root {\n  --color-text-body: ${PAIR};\n}\n`,
      "modules/x/ui/x.module.css": USES_TOKEN,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })
})

describe("規則 v：元件層的自訂屬性不可跨檔引用", () => {
  it("模組 CSS 宣告的自訂屬性被別的檔案引用會被擋 —— --sidebar-width 就是這樣跨層的", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "config/shell/shell.module.css": `${USES_TOKEN}.b { --rail: var(--color-text-body); }\n`,
      "config/shell/Shell.tsx": `${USES_CLASS}export const B = () => <p className={s.b} />\n`,
      "shared/ui/styles/kit.module.css": `.c { color: var(--rail); }\n`,
      "shared/ui/Kit.tsx": `import u from "./styles/kit.module.css"\nexport const C = () => <p className={u.c} />\n`,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("不可跨檔引用"))
  })

  it("同一個檔案裡自己宣告自己用是正常的 —— 那正是元件層 token 的用途", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css":
        `.a { --pad: var(--color-text-body); }\n.b { color: var(--pad); }\n`,
      "modules/x/ui/X.tsx":
        `${USES_CLASS}export const B = () => <p className={s.b} />\n`,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("覆寫語意層 token 放行 —— 斷點上改側欄寬度是合法寫法", () => {
    const root = fixture({
      "app/tokens/base.css": `:root {\n  --color-text-body: #374151;\n  --layout-rail: 216px;\n}\n`,
      "config/shell/shell.module.css":
        `.shell { --layout-rail: 0; }\n.a { color: var(--color-text-body); }\n`,
      "config/shell/Shell.tsx":
        `import s from "./shell.module.css"\nexport const A = () =>`
        + ` <p className={s.shell}><i className={s.a} /></p>\n`,
      "shared/ui/styles/kit.module.css": `.c { width: calc(100% - var(--layout-rail)); }\n`,
      "shared/ui/Kit.tsx": `import u from "./styles/kit.module.css"\nexport const C = () => <p className={u.c} />\n`,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })
})

describe("規則 i：自訂屬性與算式", () => {
  it("模組 CSS 的自訂屬性寫死 px 會被擋", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `${USES_TOKEN}.b { --pad: 13px; padding: var(--pad); }\n`,
      "modules/x/ui/X.tsx": `${USES_CLASS}export const B = () => <p className={s.b} />\n`,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("--pad 不可寫死 13px"))
  })

  it("CSS 字串裡的 --x: 不是宣告 —— content 的內容不可以被當成 token", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `${USES_TOKEN}.b { content: "--fake: 99px"; }\n`,
      "modules/x/ui/X.tsx": `${USES_CLASS}export const B = () => <p className={s.b} />\n`,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("同一行的第二條宣告仍然收得到 —— 跳過引號不可以連宣告一起跳掉", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `${USES_TOKEN}.b { --pad: 4px; --gap: 13px; }\n`,
      "modules/x/ui/X.tsx": `${USES_CLASS}export const B = () => <p className={s.b} />\n`,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("--gap 不可寫死 13px"))
  })

  it("與 env(safe-area-*) 相加的 px 是元件尺寸，兩種寫順序都放行", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css":
        `${USES_TOKEN}.b {\n`
        + `  min-height: calc(60px + env(safe-area-inset-top));\n`
        + `  max-height: calc(env(safe-area-inset-top) + 60px);\n}\n`,
      "modules/x/ui/X.tsx": `${USES_CLASS}export const B = () => <p className={s.b} />\n`,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("算式裡的留白兩種寫順序都要擋 —— 判準不可以跟著寫法變", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css":
        `${USES_TOKEN}.b { width: calc(100vw - 32px); max-width: calc(32px + 100vw); }\n`,
      "modules/x/ui/X.tsx": `${USES_CLASS}export const B = () => <p className={s.b} />\n`,
    })
    expect(collectTokenErrors(root).filter((e) => e.includes("32px"))).toHaveLength(2)
  })
})

describe("規則 g：跨行寫的 media query", () => {
  it("條件換行寫一樣要檢查斷點 —— 逐行看會整條漏掉", () => {
    const root = fixture({
      "app/tokens/base.css": TOKENS,
      "modules/x/ui/x.module.css": `${USES_TOKEN}@media\n  (max-width: 999px) {\n  .a { color: red; }\n}\n`,
      "modules/x/ui/X.tsx": USES_CLASS,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("斷點 999px"))
  })
})

describe("規則 t：行內樣式的裸色值與節奏類數字", () => {
  // token 檔宣告的每個 token 都要有人引用（規則 b），所以每個 fixture 都順手用掉它。
  const U_TOKENS = `:root {\n  --color-text-body: #374151;\n  --space-6: 24px;\n}\n`
  const TSX = (style: string) =>
    "export const A = () => <p style={{ "
    + `color: "var(--color-text-body)", padding: "var(--space-6)", ${style} }}>x</p>\n`

  it("JSX 的裸數字就是 px，會被擋", () => {
    const root = fixture({
      "app/tokens/base.css": U_TOKENS,
      "modules/x/ui/X.tsx": TSX("paddingTop: 24"),
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("paddingTop 不可寫死 24px"))
  })

  it("字串值裡的 px 一樣要擋", () => {
    const root = fixture({
      "app/tokens/base.css": U_TOKENS,
      "modules/x/ui/X.tsx": TSX(`margin: "16px 0 24px"`),
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("16px"))
  })

  it("行內樣式的裸色值會被擋", () => {
    const root = fixture({
      "app/tokens/base.css": U_TOKENS,
      "modules/x/ui/X.tsx": TSX(`background: "#ffffff"`),
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("行內樣式不可寫死色值"))
  })

  it("3px 以下是光學微調，放行 —— 必填星號的 marginLeft 就是這一類", () => {
    const root = fixture({
      "app/tokens/base.css": U_TOKENS,
      "modules/x/ui/X.tsx": TSX("marginLeft: 2"),
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("尺寸屬性的值本身放行，樣板字串裡的算式不誤判 —— Modal 的 width 就是這樣寫的", () => {
    const root = fixture({
      "app/tokens/base.css": U_TOKENS,
      "modules/x/ui/X.tsx":
        "export const A = ({ w }: { w: number }) => <p style={{"
        + ' color: "var(--color-text-body)", padding: "var(--space-6)",'
        + " width: w ? `min(100%, ${w}px)` : undefined, maxWidth: 520 }}>x</p>\n",
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("算式裡當留白的 px 仍然要擋", () => {
    const root = fixture({
      "app/tokens/base.css": U_TOKENS,
      "modules/x/ui/X.tsx": TSX(`width: "calc(100vw - 32px)"`),
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("32px"))
  })

  it("註解掉的行內樣式不可以被報 —— 假陽性比漏報更傷檢查器", () => {
    const root = fixture({
      "app/tokens/base.css": U_TOKENS,
      "modules/x/ui/X.tsx":
        "// 舊寫法：<p style={{ padding: 24 }} />\n"
        + `export const A = () => <p style={{ color: "var(--color-text-body)",`
        + ` padding: "var(--space-6)" }}>x</p>\n`,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("正規式裡的 // 不是註解 —— 抹掉整行後面會讓同行的 styles.x 消失", () => {
    const root = fixture({
      "app/tokens/base.css": U_TOKENS,
      "modules/x/ui/x.module.css": `.after { color: var(--color-text-body); padding: var(--space-6); }\n`,
      "modules/x/ui/X.tsx":
        `import s from "./x.module.css"\n`
        + `const abs = (u: string) => /^https?:\\/\\//.test(u)\n`
        + `export const A = () => <p className={s.after} title={String(abs)} />\n`,
    })
    expect(collectTokenErrors(root)).toEqual([])
  })

  it("字串裡的 // 不是註解 —— 不可以把後面的內容一起吃掉", () => {
    const root = fixture({
      "app/tokens/base.css": U_TOKENS,
      "modules/x/ui/X.tsx":
        `const url = "https://example.com"\n`
        + `export const A = () => <a href={url} style={{ color: "var(--color-text-body)",`
        + ` padding: "var(--space-6)", marginTop: 24 }}>x</a>\n`,
    })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("marginTop 不可寫死 24px"))
  })

  it("走 token 的行內樣式全綠", () => {
    const root = fixture({
      "app/tokens/base.css": U_TOKENS,
      "modules/x/ui/X.tsx": TSX(`gap: "var(--space-6)"`),
    })
    expect(collectTokenErrors(root)).toEqual([])
  })
})

describe("規則 u：manifest 的 theme_color 必須等於預設主題的底色", () => {
  const TREE = (themeColor: string) => ({
    "app/tokens/primitives.css": `:root {\n  --ds-gray-950: #0F1115;\n}\n`,
    "app/themes/default.css": `:root {\n  --color-bg-app: var(--ds-gray-950);\n}\n`,
    "app/layout.tsx":
      `import "./tokens/primitives.css"\nimport "./themes/default.css"\nexport default null\n`,
    "app/manifest.ts": `export default () => ({ theme_color: "${themeColor}" })\n`,
    "config/theme.ts": `export type ThemeName = "default"\nexport const DEFAULT_THEME: ThemeName = "default"\n`,
    "modules/x/ui/x.module.css": `.a { background: var(--color-bg-app); }\n`,
    "modules/x/ui/X.tsx": USES_CLASS,
  })

  it("theme_color 與主題底色不一致會被擋 —— 換主題時最容易漏掉的一行", () => {
    const root = fixture(TREE("#000000"))
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("theme_color"))
  })

  it("一致就放行，而且是**解析後**比對，不是比字面", () => {
    expect(collectTokenErrors(fixture(TREE("#0F1115")))).toEqual([])
  })

  it("大小寫不同不算不一致", () => {
    expect(collectTokenErrors(fixture(TREE("#0f1115")))).toEqual([])
  })
})

describe("檢查器本身", () => {
  it("掃到空集合時要報錯，不可以安靜地綠燈", () => {
    const root = fixture({ "readme.md": "no css here\n" })
    expect(collectTokenErrors(root)).toContainEqual(expect.stringContaining("掃不到"))
  })

  /**
   * 規則清單是這份 repo 裡最會漂的東西 —— 加了規則忘了寫進文件、或文件留著已經拿掉的
   * 規則，兩種都不會有任何訊號。這條把兩邊釘在一起。
   */
  it("文件的規則對照表與實作必須是同一組", () => {
    const letters = (source: string, pattern: RegExp) =>
      [...new Set([...source.matchAll(pattern)].map((match) => match[1]))].sort()

    // 路徑相對於 vitest 的 root（`apps/web`）。讀不到會直接拋，不會安靜空過。
    const checker = readFileSync(path.resolve("scripts/check-tokens.mjs"), "utf8")
    const doc = readFileSync(path.resolve("../../docs/design-system.md"), "utf8")
    // 實作的標記是 JSDoc 的 `x：`。`b` 寫在 `a` 那條的句子裡（`a：…。b：…`），
    // 所以前面要收得到全形句號。
    expect(letters(checker, /(?:^|[\s*。])([a-z])：/gm)).toEqual(letters(doc, /^\| ([a-z]) \|/gm))
  })
})
