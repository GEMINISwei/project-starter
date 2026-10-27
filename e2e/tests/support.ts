import { expect, type Page } from "@playwright/test"

// 超管由 `make check e2e` 以 CLI 建立 (網頁上沒有建立超管的入口), 帳密每次隨機產生。
export const admin = {
  username: requireEnv("E2E_ADMIN_USERNAME"),
  password: requireEnv("E2E_ADMIN_PASSWORD"),
}

// 一般帳號由 users.spec.ts 的第一個測試在畫面上建立。資料庫每次都是新的, 名稱固定即可。
export const member = {
  nickname: "E2E 一般帳號",
  username: "e2e-member",
  password: "e2e-member-password",
}

function requireEnv(name: string): string {
  const value = process.env[name]
  if (!value) throw new Error(`缺少 ${name}：請在 repo 根目錄用 make check e2e 執行`)
  return value
}

export async function login(page: Page, account: { username: string; password: string }) {
  await page.goto("/login")
  await page.getByRole("textbox", { name: "帳號" }).fill(account.username)
  await page.getByLabel("密碼", { exact: true }).fill(account.password)
  await page.getByRole("button", { name: "登入", exact: true }).click()
  await expect(page).toHaveURL("/")
}

export async function logout(page: Page) {
  await page.getByRole("button", { name: "帳號選單" }).click()
  await page.getByRole("menuitem", { name: "登出" }).click()
  await expect(page).toHaveURL(/\/login/)
}
