import "server-only"
import { getCurrentUser } from "@/modules/auth/public.server"
import { apiGet } from "@/shared/api/request.server"
import { getApiItemData } from "@/shared/api/response"
import { getT } from "@/shared/i18n/locale.server"
import { settingsMessages } from "./i18n"
import SettingsView from "./ui/SettingsView"

export async function generateMetadata() {
  return { title: (await getT(settingsMessages))("pageTitle") }
}

export default async function SettingsPage() {
  // getCurrentUser() 有 React `cache()`, 同一次 render 內與外殼共用同一筆結果。
  const [{ data }, versionRes, t] = await Promise.all([
    getCurrentUser(),
    // 版號以後端的 APP_VERSION 為準: 只有它跟著發版, web 的 package.json 不跟。
    apiGet({ url: "/system/version" }),
    getT(settingsMessages),
  ])
  const version = getApiItemData(versionRes)?.version ?? t("versionUnavailable")
  return <SettingsView nickname={data?.nickname ?? ""} version={version} />
}
