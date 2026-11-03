import { randomUUID } from "node:crypto"
import { expect } from "@playwright/test"
import { SIGNED_OUT, createUser, login, logout, test } from "./support"

// 預設載入超管的登入狀態 (playwright.config.ts)。
test("超級管理者新增使用者後，列表看得到該使用者", async ({ page }) => {
  const id = randomUUID().slice(0, 8)
  const nickname = `E2E 新使用者 ${id}`
  await page.goto("/admin/users")

  await page.getByRole("button", { name: "新增使用者" }).click()
  const dialog = page.getByRole("dialog")
  await dialog.getByLabel("暱稱").fill(nickname)
  await dialog.getByLabel("帳號").fill(`e2e-new-${id}`)
  await dialog.getByLabel("密碼").fill(`e2e-password-${id}`)
  await dialog.getByRole("button", { name: "建立", exact: true }).click()

  await expect(dialog).toBeHidden()
  // 列表在桌面寬度下沒有帳號欄, 以暱稱辨認。
  await expect(page.getByRole("cell", { name: nickname, exact: true })).toBeVisible()
})

test.describe("一般帳號", () => {
  test.use({ storageState: SIGNED_OUT })

  test("一般帳號進入管理區會被導回首頁", async ({ page, member }) => {
    await login(page, member)

    await page.goto("/admin/users")

    await expect(page).toHaveURL("/")
  })

  test("登出後其他已登入的裝置也會被登出", async ({ browser }) => {
    // 登出會撤銷這個帳號所有裝置的 session, 用 worker 共用的 member 會連累同一個 worker 之後的測試。
    const account = await createUser(browser, "logout")
    // 兩個 context 不共用 cookie, 等於兩台裝置。
    const deviceA = await browser.newContext({ storageState: SIGNED_OUT })
    const deviceB = await browser.newContext({ storageState: SIGNED_OUT })
    const pageA = await deviceA.newPage()
    const pageB = await deviceB.newPage()
    await login(pageA, account)
    await login(pageB, account)

    await logout(pageA)

    // B 的 cookie 還在, 擋下它的是後端的 auth_version 比對。
    await pageB.goto("/settings")
    await expect(pageB).toHaveURL(/\/login/)

    await deviceA.close()
    await deviceB.close()
  })
})
