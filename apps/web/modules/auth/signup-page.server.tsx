import { redirect } from "next/navigation"
import { getT } from "@/shared/i18n/locale.server"
import { authMessages } from "./i18n"
import { getBootstrapState } from "./bootstrap.server"
import SignupForm from "./ui/SignupForm"

export async function generateMetadata() {
  return { title: (await getT(authMessages))("signupTitle") }
}

export default async function SignupPage() {
  // 註冊頁只在「系統還沒有超級管理者」時有意義。已經初始化完的部署不留任何入口 ——
  // 直接導回登入，而不是顯示一頁「已完成初始化」讓人再點一次。
  //
  // 真正的把關永遠在後端（system_state 的唯一鍵 + transaction），這裡影響的只是
  // 「顯示什麼」，不是「能不能建立」。所以 "unknown"（查詢失敗）仍然顯示表單：
  // 總比因為一次網路抖動就讓人無法初始化好。
  if (await getBootstrapState() === "completed") {
    redirect("/login")
  }

  return <SignupForm />
}
