/**
 * `shared/` 自己擁有的使用者可見字串。
 *
 * 只收「不屬於任何模組、也不屬於 UI kit」的那幾條 —— UI kit 的在 `shared/ui/i18n.ts`
 * （它有自己的公開面，文案是它的實作細節），模組的在各模組的 `i18n.ts`。
 *
 * 這裡**不是**全站字典。`shared/` 不可以引用 `modules/`，所以中央字典在這個架構下
 * 根本組不出來；而且真的組出來的話，刪掉一個模組就得回頭清理 shared。
 */

import { defineMessages } from "./dictionary"

export const sharedMessages = defineMessages({
  zh: {
    passwordRequired: "請輸入密碼",
    passwordTooShort: "至少 {min} 個字元",
    passwordTooLong: "不可超過 {max} bytes",
    currentUserFailed: "無法取得目前使用者資訊",
    systemNotice: "系統通知",
  },
  en: {
    passwordRequired: "Password is required",
    passwordTooShort: "At least {min} characters",
    passwordTooLong: "Must not exceed {max} bytes",
    currentUserFailed: "Failed to load the current user",
    systemNotice: "System notification",
  },
})
