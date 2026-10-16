import "server-only"
import { getCurrentUser } from "@/modules/auth/public.server"
import { getT } from "@/shared/i18n/locale.server"
// 只在 server 端讀: 這個檔案不進瀏覽器的 bundle, 送出去的只有下面那一個版號字串。
import packageJson from "@/package.json"
import { settingsMessages } from "./i18n"
import SettingsView from "./ui/SettingsView"

export async function generateMetadata() {
  return { title: (await getT(settingsMessages))("pageTitle") }
}

export default async function SettingsPage() {
  // getCurrentUser() 有 React `cache()`, 同一次 render 內與外殼共用同一筆結果。
  const { data } = await getCurrentUser()
  // 讀 web 自己的 package.json 而不是問後端: 整個 repo 只有一個版號, 各份副本由
  // `make release` 一起改、`make check` 擋住不一致, 所以這裡就是系統的版號。
  return <SettingsView nickname={data?.nickname ?? ""} version={packageJson.version} />
}
