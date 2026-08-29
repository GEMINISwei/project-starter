import { describe, expect, it } from "vitest"
import { urlBase64ToUint8Array } from "@/modules/push/encoding"

/**
 * 只測 `encoding.ts` 裡的純函式。其餘（registerServiceWorker、subscribe…）都是對
 * `navigator.serviceWorker` / `Notification` 的包裝，要測得先把整組瀏覽器 API 造出來，
 * 而測到的其實是 mock 本身 —— 成本高、訊號低，刻意不納入。
 *
 * `urlBase64ToUint8Array` 值得測：VAPID 公鑰是 base64**url** 編碼（用 `-`/`_` 取代
 * `+`/`/` 且不補 `=`），轉錯的表現是推播訂閱在瀏覽器端被拒絕，錯誤訊息與金鑰無關，
 * 很難往回追到這個函式。
 */
describe("urlBase64ToUint8Array", () => {
  it("把標準 base64 轉成對應的位元組", () => {
    // "Hi" -> base64 "SGk="；已經帶 padding，不需要補。
    expect(Array.from(urlBase64ToUint8Array("SGk="))).toEqual([72, 105])
  })

  it("長度不是 4 的倍數時自動補上 padding", () => {
    // "Hi" 的 base64 去掉 "=" 之後是 "SGk"，VAPID 公鑰就是這種沒有 padding 的形式。
    expect(Array.from(urlBase64ToUint8Array("SGk"))).toEqual([72, 105])
  })

  it("把 base64url 的 - 與 _ 還原成 + 與 /", () => {
    // 0xFB 0xFF 0xBF 的標準 base64 是 "+/+/"，base64url 形式則是 "-_-_"。
    const standard = Array.from(urlBase64ToUint8Array("+/+/"))
    const urlSafe = Array.from(urlBase64ToUint8Array("-_-_"))

    expect(urlSafe).toEqual(standard)
  })

  it("回傳的是 Uint8Array，長度與解碼後的位元組數一致", () => {
    const result = urlBase64ToUint8Array("SGVsbG8")

    expect(result).toBeInstanceOf(Uint8Array)
    expect(result.length).toBe(5) // "Hello"
  })

  it("空字串回傳空陣列而不是爆掉", () => {
    expect(urlBase64ToUint8Array("").length).toBe(0)
  })
})
