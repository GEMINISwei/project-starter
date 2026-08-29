import fs from "node:fs"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"
import { SUPPORTED_LOCALES } from "@/shared/i18n/locale"
import { ADMIN_ROUTES, PROTECTED_ROUTES, isProtectedPathname } from "@/config/routes"

const SRC = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..")

/**
 * `app/` 底下每個 `page.tsx` 對應的網址路徑。
 *
 * route group（`(protected)`、`(admin)`）只用來共用 layout，不出現在網址裡，所以剝掉。
 */
function routePathsOnDisk(): string[] {
  const paths: string[] = []
  function walk(dir: string, segments: string[]) {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      if (entry.isDirectory()) {
        const isGroup = entry.name.startsWith("(") && entry.name.endsWith(")")
        walk(path.join(dir, entry.name), isGroup ? segments : [...segments, entry.name])
      } else if (entry.name === "page.tsx") {
        paths.push(`/${segments.join("/")}`.replace(/\/$/, "") || "/")
      }
    }
  }
  walk(path.join(SRC, "app"), [])
  return paths
}

describe("isProtectedPathname", () => {
  it("清單裡的每一條路由都受保護", () => {
    for (const route of PROTECTED_ROUTES) {
      expect(isProtectedPathname(route.path)).toBe(true)
    }
  })

  it("子路徑也受保護", () => {
    expect(isProtectedPathname("/roles/abc123/edit")).toBe(true)
    expect(isProtectedPathname("/users/1")).toBe(true)
  })

  it("只是前綴相同的無關路徑不會被誤判", () => {
    // 這是 startsWith 最常見的 bug：/usersomething 並不是 /users 的子頁面。
    expect(isProtectedPathname("/usersomething")).toBe(false)
    expect(isProtectedPathname("/settingsx")).toBe(false)
  })

  it("公開路徑不受保護", () => {
    expect(isProtectedPathname("/login")).toBe(false)
    expect(isProtectedPathname("/signup")).toBe(false)
    expect(isProtectedPathname("/")).toBe(false)
  })
})

describe("PROTECTED_ROUTES", () => {
  it("路徑不重複", () => {
    const paths = PROTECTED_ROUTES.map((route) => route.path)
    expect(new Set(paths).size).toBe(paths.length)
  })

  it("每條路由都有以 / 開頭的路徑，且每個語系都有非空標籤", () => {
    for (const route of PROTECTED_ROUTES) {
      expect(route.path.startsWith("/")).toBe(true)
      // 逐一檢查每個語系：只看 zh 的話，漏翻的 en 會在導覽列上變成 undefined。
      for (const locale of SUPPORTED_LOCALES) {
        expect(route.label[locale].length).toBeGreaterThan(0)
      }
    }
  })

  it("每條路由都明確宣告 requires（可以是空陣列，但不能忘了寫）", () => {
    for (const route of PROTECTED_ROUTES) {
      expect(Array.isArray(route.requires)).toBe(true)
    }
  })

  it("ADMIN_ROUTES 就是 group 為 admin 的那些路由", () => {
    expect(ADMIN_ROUTES.map((route) => route.path)).toEqual(["/users", "/roles"])
  })

  it("admin 區的每條路由都要求權限，不會意外對所有登入者開放", () => {
    for (const route of ADMIN_ROUTES) {
      expect(route.requires.length).toBeGreaterThan(0)
    }
  })

  /**
   * 這條守的是新增模組時**唯一還會安靜失敗**的一步。
   *
   * `ENABLED_MODULES` 加了一筆卻忘了在 `app/` 建 route adapter，側欄會多一個連結、
   * proxy 會保護那個路徑，但點下去是 404 —— 沒有編譯錯誤，也沒有測試會紅。
   * （反方向不必檢查：adapter 存在但沒登記，頁面仍可直接訪問，是刻意允許的。）
   */
  it("每條路由在 app/ 都有對應的 route adapter", () => {
    const onDisk = new Set(routePathsOnDisk())
    const missing = PROTECTED_ROUTES.map((route) => route.path).filter(
      (routePath) => !onDisk.has(routePath),
    )

    expect(missing).toEqual([])
  })
})
