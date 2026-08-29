import { defineMessages } from "@/shared/i18n/dictionary"

export const settingsMessages = defineMessages({
  zh: {
    pageTitle: "系統設定",
    notificationSection: "通知設定",
    pushNotification: "推播通知",
    pushUnsupported: "請先將此應用程式加入主畫面（安裝為 Web App）以使用推播通知",
    pushDenied: "已在瀏覽器中封鎖，請至瀏覽器設定手動開啟",
    languageSection: "語言",
    languageName: "顯示語言",
    languageDesc: "同時決定伺服器回傳的訊息語言",
    localeZh: "繁體中文",
    localeEn: "English",
  },
  en: {
    pageTitle: "Settings",
    notificationSection: "Notifications",
    pushNotification: "Push notifications",
    pushUnsupported: "Add this app to your home screen (install as a web app) to enable push notifications",
    pushDenied: "Blocked by the browser. Enable it in your browser settings.",
    languageSection: "Language",
    languageName: "Display language",
    languageDesc: "Also selects the language of server messages",
    localeZh: "繁體中文",
    localeEn: "English",
  },
})
