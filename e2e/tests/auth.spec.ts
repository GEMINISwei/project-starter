import { expect, test } from "@playwright/test"
import { admin, login } from "./support"

test("未登入進受保護頁面會導向登入頁", async ({ page }) => {
  await page.goto("/settings")

  await expect(page).toHaveURL(/\/login/)
})

test("登入成功後進入首頁，session cookie 為 httpOnly", async ({ page, context }) => {
  await login(page, admin)

  await expect(page.getByText("請從左側選單選擇功能開始使用。")).toBeVisible()
  const cookies = await context.cookies()
  const session = cookies.find((cookie) => cookie.name === "access_token")
  expect(session?.httpOnly).toBe(true)
  expect(session?.sameSite).toBe("Lax")
})

test("帳號或密碼錯誤時留在登入頁並顯示錯誤訊息", async ({ page }) => {
  await page.goto("/login")
  await page.getByRole("textbox", { name: "帳號" }).fill(admin.username)
  await page.getByLabel("密碼", { exact: true }).fill("wrong-password")
  await page.getByRole("button", { name: "登入", exact: true }).click()

  // 文案來自後端的 LangText, 依請求的語系回傳。
  await expect(page.getByText("帳號或密碼錯誤")).toBeVisible()
  await expect(page).toHaveURL(/\/login/)
})
