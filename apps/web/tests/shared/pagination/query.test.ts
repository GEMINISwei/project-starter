import { describe, expect, it } from "vitest"
import { parseBooleanFilter, parsePagination } from "@/shared/pagination/query"

describe("parsePagination", () => {
  it("沒有參數時退回第一頁、往後翻", () => {
    expect(parsePagination()).toEqual({ cursor: undefined, direction: "next", seq: 1 })
  })

  it("只有 direction=prev 會被當成往前翻，其他值一律視為 next", () => {
    expect(parsePagination({ direction: "prev" }).direction).toBe("prev")
    expect(parsePagination({ direction: "next" }).direction).toBe("next")
    expect(parsePagination({ direction: "PREV" }).direction).toBe("next")
    expect(parsePagination({ direction: "亂填" }).direction).toBe("next")
  })

  it("seq 只接受正整數，其餘一律退回 1", () => {
    // seq 只用來顯示頁碼，被亂填時不該讓畫面出現 NaN 或負數頁。
    expect(parsePagination({ seq: "3" }).seq).toBe(3)
    expect(parsePagination({ seq: "0" }).seq).toBe(1)
    expect(parsePagination({ seq: "-2" }).seq).toBe(1)
    expect(parsePagination({ seq: "abc" }).seq).toBe(1)
    expect(parsePagination({ seq: "" }).seq).toBe(1)
  })

  it("cursor 原樣傳遞（它對前端是不透明字串）", () => {
    expect(parsePagination({ cursor: "WyIyMDI2Il0=" }).cursor).toBe("WyIyMDI2Il0=")
  })
})

describe("parseBooleanFilter", () => {
  it("只接受 API 支援的布林字串", () => {
    expect(parseBooleanFilter("true")).toBe("true")
    expect(parseBooleanFilter("false")).toBe("false")
    expect(parseBooleanFilter("TRUE")).toBe("")
    expect(parseBooleanFilter("1")).toBe("")
    expect(parseBooleanFilter()).toBe("")
  })
})
