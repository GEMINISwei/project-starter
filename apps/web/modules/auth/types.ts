// login 與 signup 是同一個模組的兩個頁面, 型別收在同一個 `types.ts`——
// 模組的公開形狀由 `public.server.ts` 決定, 內部不再另外分層。

// ---- 登入 ----

// 導向原因是 shared 與 auth 共用的約定, 定義在 shared (理由見那份檔案)。
export type { LoginRedirectReason } from "@/shared/session/login-contract"

export type LoginFormValues = {
  username: string
  password: string
}

export type LoginFormErrors = Partial<Record<keyof LoginFormValues, string>>

// ---- 註冊 ----

export type SignupFormValues = {
  register_key: string
  username: string
  nickname: string
  password: string
}

export type SignupFormErrors = Partial<Record<keyof SignupFormValues, string>>
