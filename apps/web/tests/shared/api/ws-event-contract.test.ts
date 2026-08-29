import { readFileSync } from "node:fs"
import path from "node:path"
import { describe, expect, it } from "vitest"

/**
 * `WsEvent` 信封的欄位必須與後端一致。
 *
 * **這是全專案最後一個「改了不會有任何訊號」的前後端接縫。** WebSocket 訊息不經過 HTTP，
 * 所以永遠不會進 OpenAPI，`make gen-types` 幫不上忙 —— `contracts/README.md` 把它記為
 * 刻意的缺口。但那句話解釋的是「**不能從 OpenAPI 產生**」，不是「不能被檢查」。
 *
 * 同一個模式（讓重複變成**可驗證**的重複）這個 repo 已經用了兩次，都在 `check-tokens.mjs`：
 * `ICON_SIZE`／`DROPDOWN_WIDTH` 的成對數字，與 manifest 的 `theme_color` 對主題底色。
 * 這是第三次，用在唯一剩下的那個接縫上。
 *
 * 跨 app 讀檔有先例：`tests/scripts/check-tokens.test.ts` 就在讀 `docs/design-system.md`。
 */

const SCHEMA = path.resolve("../api/modules/realtime/schema.py")
const ENTITIES = path.resolve("shared/api/entities.ts")

/** 後端 `class WsEvent(BaseModel):` 宣告的欄位名。 */
function backendFields(): string[] {
  const source = readFileSync(SCHEMA, "utf8")
  const block = source.match(/class WsEvent\(BaseModel\):\n([\s\S]*?)(?=\nclass |\n@|$)/)
  if (!block) throw new Error(`${SCHEMA} 找不到 class WsEvent(BaseModel)，這條測試已經失效`)
  // docstring 先剝掉：它的縮排與欄位相同，而「一行英文小寫字接冒號」會被誤認成欄位。
  const body = block[1].replace(/"""[\s\S]*?"""/g, "")
  return [...body.matchAll(/^ {4}([a-z_][a-z0-9_]*)\s*:/gm)].map((match) => match[1])
}

/** 前端 `export type WsEvent = { … }` 宣告的欄位名。 */
function frontendFields(): string[] {
  const source = readFileSync(ENTITIES, "utf8")
  const block = source.match(/export type WsEvent = \{\n([\s\S]*?)\n\}/)
  if (!block) throw new Error(`${ENTITIES} 找不到 export type WsEvent，這條測試已經失效`)
  return [...block[1].matchAll(/^ {2}([a-z_][a-z0-9_]*)\??\s*:/gm)].map((match) => match[1])
}

describe("WsEvent 信封的前後端對齊", () => {
  // 解析不到欄位時「兩邊都是空的」會讓下面那條變成恆真。寧可誤報也不要安靜綠燈
  // （同 contrast.test.ts 的「掃得到主題檔」與 check-tokens.mjs 的空集合守衛）。
  it("兩邊都解析得出欄位", () => {
    expect(backendFields().length).toBeGreaterThan(0)
    expect(frontendFields().length).toBeGreaterThan(0)
  })

  it("欄位名必須是同一組", () => {
    expect([...frontendFields()].sort()).toEqual([...backendFields()].sort())
  })
})
