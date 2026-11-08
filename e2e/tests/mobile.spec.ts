import { expect } from "@playwright/test"
import { test } from "./support"

// WebApp 在手機上要像原生 App: 點輸入框不放大畫面。iOS Safari 會在輸入框字級小於 16px 時
// 放大畫面, 所以觸控裝置上的輸入框字級要至少 16px。不用 `maximum-scale=1` 擋縮放:
// 那也會擋掉使用者自己的雙指縮放。
test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })

test("輸入框字級至少 16px，點擊時不會放大畫面", async ({ page }) => {
  await page.goto("/settings")

  const inputs = page.locator("input:not([type=hidden]), select")
  await expect(inputs.first()).toBeVisible()
  const sizes = await inputs.evaluateAll((elements) =>
    elements.map((element) => Number.parseFloat(getComputedStyle(element).fontSize)),
  )

  expect(sizes.length).toBeGreaterThan(0)
  for (const size of sizes) expect(size).toBeGreaterThanOrEqual(16)
})
