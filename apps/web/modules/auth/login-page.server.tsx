import { redirect } from "next/navigation"
import { getT } from "@/shared/i18n/locale.server"
import { authMessages } from "./i18n"
import { getBootstrapState } from "./bootstrap.server"
import LoginForm from "./ui/LoginForm"
import { getLoginRedirectReason } from "./validation"

// 標題跟著語系走，所以是 generateMetadata 而不是靜態 metadata。
// route adapter 要轉出的名字也跟著改（見 app/(public)/login/page.tsx）。
export async function generateMetadata() {
  return { title: (await getT(authMessages))("loginTitle") }
}

export type LoginPageProps = {
  searchParams?: Promise<{
    reason?: string | string[]
  }>
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  // 系統還沒有超級管理者時，登入頁沒有任何人能用 —— 直接把人帶去初始化。
  // 這是「未初始化就進註冊畫面」的唯一觸發點：proxy.ts 會把未登入的 `/` 導到這裡，
  // 剩下的判斷留在這一層做，不讓 edge middleware 每個請求都去打後端。
  //
  // 只有明確得到 "available" 才導向；查詢失敗（"unknown"）留在登入頁。
  if (await getBootstrapState() === "available") {
    redirect("/signup")
  }

  const params = await searchParams

  return (
    <LoginForm reason={getLoginRedirectReason(params?.reason)} />
  )
}
