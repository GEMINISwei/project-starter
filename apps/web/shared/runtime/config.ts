/**
 * 「可以公開給瀏覽器」的部署設定，**執行期**才決定值。
 *
 * 為什麼不用 `NEXT_PUBLIC_*`：那一組會在 `next build` 當下被字面內嵌進 client bundle，
 * 等於把部署設定烤進 image —— 同一份 image 就不能部署到第二個環境，而且改了主機 `.env`
 * 畫面不會變，也沒有任何錯誤訊息。所以這裡的值一律走「伺服器端讀 `process.env` →
 * 經 provider 傳給 client」，代價是多一層 context。
 *
 * 刻意**不放**這裡的兩項：VERSION（唯一一份是 `apps/api/app/config.py` 的 `APP_VERSION`，
 * 前端要顯示就跟 API 拿）與 `API_URL`（compose 內網位址，只有伺服器端用得到，
 * 放進來等於把內部拓撲送到瀏覽器）。
 */

export type PublicConfig = {
  /** 顯示在側欄、分頁標題與 PWA 名稱上的系統名稱（`.env` 的 `SYSTEM_NAME`）。 */
  systemName: string
  /** Web Push 的公鑰（`.env` 的 `VAPID_PUBLIC_KEY`）。空字串代表未啟用推播。 */
  vapidPublicKey: string
}

/**
 * 拿不到值時的退路。
 *
 * `systemName` 給 "App" 而不是空字串：空字串會讓側欄與分頁標題整個消失，看起來像渲染壞掉。
 * `vapidPublicKey` 相反 —— 空字串是**有意義的設定**（停用推播），見 `.env.example`。
 */
export const FALLBACK_PUBLIC_CONFIG: PublicConfig = {
  systemName: "App",
  vapidPublicKey: "",
}

/**
 * 只列出這個函式真的會讀的變數 —— 參數型別本身就是那份清單。
 *
 * 額外的 index signature 是為了讓 `process.env` 傳得進來：Next 會把 `NodeJS.ProcessEnv`
 * 擴充成一組具名的 key，跟這裡的具名 key 沒有交集，少了它會撞上 TypeScript 的
 * weak type detection（「兩個型別沒有共同屬性」）。
 */
type PublicConfigEnv = {
  SYSTEM_NAME?: string
  VAPID_PUBLIC_KEY?: string
  [key: string]: string | undefined
}

/**
 * 純函式，環境變數由呼叫端傳進來。直接在這裡讀 `process.env` 的話，從 client component
 * 呼叫不會報錯、但值永遠是 undefined（client bundle 裡 `process.env.X` 會變成字面 undefined）。
 *
 * 真正的入口是 `./config.server.ts`，它帶 `server-only`。分成兩層還有一個現實理由：
 * 帶 `server-only` 的模組在 jsdom 載不起來，邏輯留在這裡才測得到。
 */
export function readPublicConfig(env: PublicConfigEnv): PublicConfig {
  return {
    systemName: env.SYSTEM_NAME || FALLBACK_PUBLIC_CONFIG.systemName,
    vapidPublicKey: env.VAPID_PUBLIC_KEY ?? FALLBACK_PUBLIC_CONFIG.vapidPublicKey,
  }
}
