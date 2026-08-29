import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import path from "node:path"
import { afterEach, describe, expect, it } from "vitest"
import { collectLayoutErrors } from "../../scripts/check-boundaries.mjs"

/**
 * 檔案放置規則自己的測試。
 *
 * 依賴拓撲那一半沒有辦法用 fixture 測（它在載入時就對真的 repo 跑完了），
 * 但放置規則是純檔案系統的判斷，可以 —— 而它需要一個「確定會被擋」的樣本
 * 來證明它活著。
 */

const roots: string[] = []

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true })
})

function fixture(files: Record<string, string>) {
  const root = mkdtempSync(path.join(tmpdir(), "check-boundaries-"))
  roots.push(root)
  for (const [relative, content] of Object.entries(files)) {
    const full = path.join(root, relative)
    mkdirSync(path.dirname(full), { recursive: true })
    writeFileSync(full, content)
  }
  return root
}

/** 一個合規的最小模組。 */
const COMPLETE = {
  "modules/x/manifest.ts": "export default {}\n",
  "modules/x/i18n.ts": "export const messages = {}\n",
  "modules/x/public.server.ts": "export {}\n",
}

describe("模組底下只能有 ui/", () => {
  it("多開一層 components/ 會被擋", () => {
    const root = fixture({ ...COMPLETE, "modules/x/components/Thing.tsx": "export const A = null\n" })
    expect(collectLayoutErrors(root)).toContainEqual(expect.stringContaining("components/"))
  })

  it("hooks/ 與 utils/ 同樣要擋", () => {
    const root = fixture({
      ...COMPLETE,
      "modules/x/hooks/useThing.ts": "export const a = 1\n",
      "modules/x/utils/format.ts": "export const b = 1\n",
    })
    expect(collectLayoutErrors(root)).toHaveLength(2)
  })

  it("ui/ 底下平鋪放是對的", () => {
    const root = fixture({
      ...COMPLETE,
      "modules/x/ui/Thing.tsx": "export const A = null\n",
      "modules/x/ui/useThing.ts": "export const useThing = () => null\n",
      "modules/x/ui/thing.module.css": ".a { color: red; }\n",
    })
    expect(collectLayoutErrors(root)).toEqual([])
  })

  it("塞進 ui/ 底下一樣要擋 —— 那跟開在模組根違反的是同一件事", () => {
    const root = fixture({ ...COMPLETE, "modules/x/ui/components/Deep.tsx": "export const A = null\n" })
    expect(collectLayoutErrors(root)).toContainEqual(expect.stringContaining("ui/components/"))
  })

  it("模組根與 ui/ 底下的訊息要分得開 —— 否則不知道檔案該搬去哪", () => {
    const root = fixture({
      ...COMPLETE,
      "modules/x/hooks/useA.ts": "export const a = 1\n",
      "modules/x/ui/hooks/useB.ts": "export const b = 1\n",
    })
    const errors = collectLayoutErrors(root)
    expect(errors).toHaveLength(2)
    expect(errors.filter((e) => e.includes("模組底下只能有 ui/"))).toHaveLength(1)
    expect(errors.filter((e) => e.includes("ui/ 底下不再分層"))).toHaveLength(1)
  })
})

describe("模組的必備檔案", () => {
  it("缺 manifest.ts 會被擋", () => {
    const root = fixture({ "modules/x/i18n.ts": "export {}\n", "modules/x/public.server.ts": "export {}\n" })
    expect(collectLayoutErrors(root)).toContainEqual(expect.stringContaining("缺 manifest.ts"))
  })

  it("缺 i18n.ts 會被擋 —— 沒有它就沒有中英兩份字串的落點", () => {
    const root = fixture({ "modules/x/manifest.ts": "export {}\n", "modules/x/public.client.ts": "export {}\n" })
    expect(collectLayoutErrors(root)).toContainEqual(expect.stringContaining("缺 i18n.ts"))
  })

  it("兩個 public entry 有一個就夠 —— push 沒有頁面，只有 public.client", () => {
    const root = fixture({
      "modules/x/manifest.ts": "export {}\n",
      "modules/x/i18n.ts": "export {}\n",
      "modules/x/public.client.ts": "export {}\n",
    })
    expect(collectLayoutErrors(root)).toEqual([])
  })

  it("一個 public entry 都沒有會被擋", () => {
    const root = fixture({ "modules/x/manifest.ts": "export {}\n", "modules/x/i18n.ts": "export {}\n" })
    expect(collectLayoutErrors(root)).toContainEqual(expect.stringContaining("public.server.ts"))
  })

  it("沒有 modules/ 的樹不報錯", () => {
    expect(collectLayoutErrors(fixture({ "shared/a.ts": "export {}\n" }))).toEqual([])
  })
})
