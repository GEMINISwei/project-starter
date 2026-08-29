import { expect, test as setup } from "@playwright/test"
import { STORAGE_STATE } from "../playwright.config"

/**
 * 接縫一：一次性初始化。
 *
 * 兩邊各自都測過了 —— 後端有 `tests/modules/users/test_bootstrap.py`（併發與 transaction
 * 回滾），前端有 `tests/modules/auth/bootstrap.server.test.ts`。**沒有人測過整條**：
 * 瀏覽器進站 → 被導去 /signup → 填 REGISTER_KEY → 建立帳號 → 導去 /login → 登入 → 進站。
 *
 * 它同時是其餘 spec 的前置：登入狀態存進 STORAGE_STATE 讓後面共用。
 */

const ADMIN = {
  nickname: "E2E 管理者",
  username: "e2e-admin",
  password: "e2e-password-1234",
}

setup("未初始化的系統落在 /signup，用 REGISTER_KEY 建得起第一個超級管理者", async ({ page }) => {
  const registerKey = process.env.REGISTER_KEY ?? ""
  expect(registerKey, "REGISTER_KEY 沒有帶進來（scripts/e2e.sh 從 .env 讀）").not.toBe("")

  // 還沒有超級管理者時，任何路徑都該落在註冊頁。
  await page.goto("/")
  await expect(page).toHaveURL(/\/signup$/)

  // 用 name 而不是可見文字定位：那些文字是 i18n 的，跟著語系跑；name 不會。
  await page.fill('input[name="nickname"]', ADMIN.nickname)
  await page.fill('input[name="username"]', ADMIN.username)
  await page.fill('input[name="password"]', ADMIN.password)
  await page.fill('input[name="register_key"]', registerKey)
  await page.click('button[type="submit"]')

  await expect(page).toHaveURL(/\/login$/)

  await page.fill('input[name="username"]', ADMIN.username)
  await page.fill('input[name="password"]', ADMIN.password)
  await page.click('button[type="submit"]')

  // 登入成功會 push("/")。到得了首頁就代表 session cookie 真的簽出來、
  // 而且通得過 proxy.ts 那一層。toHaveURL 的相對路徑以 baseURL 為基準。
  await expect(page).toHaveURL("/")

  await page.context().storageState({ path: STORAGE_STATE })
})
