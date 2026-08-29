/**
 * auth 模組的 Server 公開面。
 *
 * login 與 signup 是同一個模組底下的兩個頁面，共用 `ui/auth.module.css` 與表單慣例，
 * 因此公開面收在模組根目錄的這一個檔案，而不是各自在子目錄再開一個 —— 讓
 * 「一個模組一個 public entry」這條規則沒有例外，boundary checker 也才好檢查。
 *
 * auth 沒有「模組主頁」，所以兩個頁面都用 `<name>-page.server.tsx` 命名（有主頁的
 * 模組是 `page.server.tsx` + `<name>-page.server.tsx`，例見 `modules/roles`）。
 */

export { default as LoginPage, generateMetadata as generateLoginMetadata } from "./login-page.server"
export type { LoginPageProps } from "./login-page.server"
export { default as SignupPage, generateMetadata as generateSignupMetadata } from "./signup-page.server"
