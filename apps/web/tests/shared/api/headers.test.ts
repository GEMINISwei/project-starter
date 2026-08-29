/**
 * 送給後端的 request header。
 *
 * 這裡最重要的是 **`Accept-Language`** —— 它是後端雙語能力的唯一開關
 * （後端 `shared/http/errors.py` 依它決定錯誤訊息與權限標籤的語言）。漏掉它的話後端一律
 * 回預設語系，而前端切到任何語言都看起來正常，只是訊息永遠是中文：沒有任何執行期徵兆。
 */

import { describe, expect, it } from "vitest"
import { buildRequestHeaders } from "@/shared/api/headers"

describe("Accept-Language", () => {
  it("一律送出，且跟著 locale 走", () => {
    expect(buildRequestHeaders({ locale: "zh", authRequired: true })["Accept-Language"]).toBe("zh")
    expect(buildRequestHeaders({ locale: "en", authRequired: true })["Accept-Language"]).toBe("en")
  })

  it("不需要身分的請求也要送（登入頁的錯誤訊息也該跟著語系）", () => {
    const headers = buildRequestHeaders({ locale: "en", authRequired: false })

    expect(headers["Accept-Language"]).toBe("en")
  })

  it("帶 body 時不會被 Content-Type 蓋掉", () => {
    const headers = buildRequestHeaders({ locale: "en", authRequired: true, contentType: "json" })

    expect(headers["Accept-Language"]).toBe("en")
  })
})

describe("Cookie", () => {
  it("需要身分且有 token 時帶上 access_token", () => {
    const headers = buildRequestHeaders({ locale: "zh", authRequired: true, token: "abc" })

    expect(headers["Cookie"]).toBe("access_token=abc")
  })

  it("沒有 token 就不帶", () => {
    expect(buildRequestHeaders({ locale: "zh", authRequired: true })).not.toHaveProperty("Cookie")
  })

  it("auth: \"none\" 的端點即使手上有 token 也不帶", () => {
    // 登入／註冊走這條路。把使用者的 token 送給一個不需要身分的端點沒有好處，
    // 只是把憑證多送去一個地方。
    const headers = buildRequestHeaders({ locale: "zh", authRequired: false, token: "abc" })

    expect(headers).not.toHaveProperty("Cookie")
  })
})

describe("Content-Type", () => {
  it("json 與 form-data 各自對應正確的 MIME", () => {
    expect(buildRequestHeaders({ locale: "zh", authRequired: true, contentType: "json" })["Content-Type"])
      .toBe("application/json")
    // 登入用 form-data：OAuth2 的 password flow 規定 body 是 urlencoded。
    expect(buildRequestHeaders({ locale: "zh", authRequired: true, contentType: "form-data" })["Content-Type"])
      .toBe("application/x-www-form-urlencoded")
  })

  it("沒有 body 的請求不帶 Content-Type", () => {
    expect(buildRequestHeaders({ locale: "zh", authRequired: true })).not.toHaveProperty("Content-Type")
  })
})

describe("X-Request-ID", () => {
  it("有 requestId 時原樣往後端傳", () => {
    const headers = buildRequestHeaders({ locale: "zh", authRequired: true, requestId: "abc123" })

    expect(headers["X-Request-ID"]).toBe("abc123")
  })

  it("沒有時不帶 —— 由後端自己產，這一層不該憑空造一個對不上任何上游紀錄的 id", () => {
    expect(buildRequestHeaders({ locale: "zh", authRequired: true })).not.toHaveProperty(
      "X-Request-ID",
    )
  })
})

describe("X-Real-IP", () => {
  it("有 clientIp 時往後端傳 —— 後端的限流以它為 key", () => {
    const headers = buildRequestHeaders({
      locale: "zh",
      authRequired: false,
      clientIp: "203.0.113.9",
    })

    expect(headers["X-Real-IP"]).toBe("203.0.113.9")
  })

  it("沒有時不帶，讓後端退回 peer address", () => {
    expect(buildRequestHeaders({ locale: "zh", authRequired: false })).not.toHaveProperty(
      "X-Real-IP",
    )
  })
})
