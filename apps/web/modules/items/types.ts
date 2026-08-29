import type { components } from "@/shared/api/generated/schema"

// 跨模組共用的 entity 從 `@/shared/api/entities` 取；`ItemInfo` 只有本模組在用，
// 所以留在這裡自己從 generated schema 衍生 —— 這樣刪掉整個 items 模組不必回頭改 shared。
// 之後若有第二個模組要用，再搬進 `entities.ts` 並把這行改成 re-export。
export type { CurrentUser } from "@/shared/api/entities"
export type ItemInfo = components["schemas"]["ItemInfo"]

export type ItemFilters = {
  name: string
  isDisabled: string
}
