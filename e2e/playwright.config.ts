import { defineConfig, devices } from "@playwright/test"

// 網址與超管帳密由 `make check e2e` 起好拋棄式 stack 之後注入 (scripts/check.sh 的 run_e2e)。
// 沒有預設值: 漏設時打到開發中的那套 (localhost:3000) 會把測試資料寫進開發資料庫。
const baseURL = process.env.E2E_BASE_URL
if (!baseURL) {
  throw new Error("缺少 E2E_BASE_URL：請在 repo 根目錄用 make check e2e 執行")
}

export default defineConfig({
  testDir: "./tests",
  // users.spec.ts 的一般帳號由畫面建立 (API 沒有對外開放), 之後的測試接著用它, 所以依序跑。
  workers: 1,
  fullyParallel: false,
  // 不重試: 重試會把時序問題藏起來, 偶發失敗要修等待條件, 不是多跑一次。
  retries: 0,
  forbidOnly: Boolean(process.env.CI),
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL,
    // 主要語系是中文, 斷言用的文案也是中文。proxy 依 Accept-Language 寫入語系 cookie。
    locale: "zh-TW",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
})
