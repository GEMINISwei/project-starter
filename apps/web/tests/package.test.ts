/**
 * dev、build、typegen 都用 Next 預設的 Turbopack (docs/decisions/0012)。
 *
 * 混用時 `make e2e` 的 dev 環境與 CI 驗的正式環境 image 差了一層打包工具, 只在其中一邊出現的問題
 * 要到另一邊才看得到。改回 webpack 時三個要一起改, 並先讀 ADR 裡的量測。
 */

import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

const PACKAGE = JSON.parse(readFileSync(path.resolve(import.meta.dirname, "../package.json"), "utf-8")) as {
  scripts: Record<string, string>
}

describe("Next 的打包工具", () => {
  it.each(["dev", "build", "typecheck"])("%s 不指定 --webpack", (name) => {
    expect(PACKAGE.scripts[name]).toMatch(/\bnext\b/)
    expect(PACKAGE.scripts[name]).not.toContain("--webpack")
  })
})
