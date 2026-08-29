/**
 * `readPublicConfig` 的重點不是「回傳正確的欄位」，是兩個 fallback 的方向相反 ——
 * 而那個不對稱從程式碼上看不出是刻意的。
 *
 * 這整個模組存在的理由是「image 建一次、部署到哪都吃當下主機的設定」，
 * 所以它處理缺值的方式必須把「少設一個變數」跟「刻意設成空」分開：前者要看得出來，
 * 後者要原樣生效。搞反的話兩種情況都只會安靜地顯示錯的東西。
 */

import { describe, expect, it } from "vitest"
import { FALLBACK_PUBLIC_CONFIG, readPublicConfig } from "@/shared/runtime/config"

describe("readPublicConfig", () => {
  it("讀傳進來的環境變數", () => {
    expect(readPublicConfig({ SYSTEM_NAME: "測試系統", VAPID_PUBLIC_KEY: "test-key" }))
      .toEqual({ systemName: "測試系統", vapidPublicKey: "test-key" })
  })

  it("systemName 沒設或為空字串都退回佔位字", () => {
    // 空字串也要走 fallback：`.env` 裡寫 `SYSTEM_NAME=` 的話側欄與分頁標題會整個消失，
    // 看起來像渲染壞掉，而不是像少設了一個變數。
    expect(readPublicConfig({}).systemName).toBe(FALLBACK_PUBLIC_CONFIG.systemName)
    expect(readPublicConfig({ SYSTEM_NAME: "" }).systemName).toBe(FALLBACK_PUBLIC_CONFIG.systemName)
  })

  it("vapidPublicKey 的空字串是有意義的設定，要原樣保留", () => {
    // 與 systemName 相反：空字串代表「停用推播」（見 .env.example），
    // 退回預設值會讓前端以為推播可用。
    expect(readPublicConfig({ VAPID_PUBLIC_KEY: "" }).vapidPublicKey).toBe("")
    expect(readPublicConfig({}).vapidPublicKey).toBe(FALLBACK_PUBLIC_CONFIG.vapidPublicKey)
  })
})
