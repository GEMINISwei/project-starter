import { expect, test } from "@playwright/test"

/**
 * 接縫二：路由保護那一層真的存在。
 *
 * `apps/web/tests/proxy.test.ts` 測的是 proxy.ts 匯出的那個函式的邏輯 —— 它證明
 * 「如果這個函式被呼叫到，判斷是對的」。它證明不了「Next 真的載到了這個檔案」。
 *
 * 而那正是 AGENTS.md 明文警告的失敗模式：proxy.ts 是 Next 的根目錄慣例檔，
 * **放錯位置不會報錯，只是路由保護那一層安靜地不存在**。這條 e2e 是那句警告的斷言版。
 */

// 這一支要的是「沒有登入」，所以把 bootstrap 存下來的登入狀態清掉。
test.use({ storageState: { cookies: [], origins: [] } })

test("未登入打受保護路由會被導去 /login", async ({ page }) => {
  await page.goto("/items")
  await expect(page).toHaveURL(/\/login/)
})

test("未登入打首頁也會被導去 /login", async ({ page }) => {
  await page.goto("/")
  await expect(page).toHaveURL(/\/login/)
})
