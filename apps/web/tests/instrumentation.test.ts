// @vitest-environment node

import { readFileSync } from "node:fs"
import path from "node:path"
import ts from "typescript"
import { afterEach, beforeEach, expect, it, vi } from "vitest"

/**
 * Next 會把 `instrumentation.ts` 同時編成 Node 與 Edge 兩個版本。Node 專用的 API 留在靜態相依裡,
 * build 與 dev 的每個請求都會印 Edge Runtime 警告, 而 build 照樣成功, 所以 `make check` 擋不到。
 */

const { requireActionsEncryptionKey } = vi.hoisted(() => ({
  requireActionsEncryptionKey: vi.fn(),
}))

vi.mock("@/shared/runtime/actions-key", () => ({ requireActionsEncryptionKey }))

const SOURCE_FILE = path.resolve(import.meta.dirname, "../instrumentation.ts")

function parseSource(): ts.SourceFile {
  return ts.createSourceFile(SOURCE_FILE, readFileSync(SOURCE_FILE, "utf8"), ts.ScriptTarget.Latest)
}

function propertyAccesses(node: ts.Node, sourceFile: ts.SourceFile): string[] {
  const own = ts.isPropertyAccessExpression(node) ? [node.getText(sourceFile)] : []
  const children: ts.Node[] = []
  ts.forEachChild(node, (child) => void children.push(child))
  return [...own, ...children.flatMap((child) => propertyAccesses(child, sourceFile))]
}

beforeEach(() => {
  requireActionsEncryptionKey.mockClear()
})

afterEach(() => {
  vi.unstubAllEnvs()
})

it("Node runtime 開機時檢查 Server Action 金鑰", async () => {
  vi.stubEnv("NEXT_RUNTIME", "nodejs")
  const { register } = await import("@/instrumentation")

  await register()

  expect(requireActionsEncryptionKey).toHaveBeenCalledOnce()
})

it("其他 runtime 不檢查金鑰", async () => {
  vi.stubEnv("NEXT_RUNTIME", "edge")
  const { register } = await import("@/instrumentation")

  await register()

  expect(requireActionsEncryptionKey).not.toHaveBeenCalled()
})

it("instrumentation 不直接使用 process.exit", () => {
  const sourceFile = parseSource()

  expect(propertyAccesses(sourceFile, sourceFile)).not.toContain("process.exit")
})

it("instrumentation 不靜態載入模組，Edge 版本才不會連帶編進 Node API", () => {
  // 上面兩個 runtime 的測試看不出這件事: 改回靜態 import, 行為相同, 只是警告回來了。
  const sourceFile = parseSource()
  const staticImports = sourceFile.statements
    .filter(ts.isImportDeclaration)
    .filter((statement) => !statement.importClause?.isTypeOnly)
    .map((statement) => statement.moduleSpecifier.getText(sourceFile))

  expect(staticImports).toEqual([])
})
