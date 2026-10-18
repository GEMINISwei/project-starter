/**
 * Next 的啟動掛勾。擋兩件「image 裡的值」與「執行期給的值」對不起來的事 —— 兩件都是
 * **沒有症狀**的失敗, 所以要在開機當下就吵。
 *
 * `UPLOAD_SIZE_LIMIT` 是唯一移不到執行期的設定 (見 next.config.ts 的 `env`): 改了主機的 .env
 * 卻沒重新建 image 時, 服務照常啟動, 只有超過舊上限的上傳會拿到莫名其妙的錯誤。
 */
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return

  requireActionsEncryptionKey()

  const built = process.env.BUILT_UPLOAD_SIZE_LIMIT
  const runtime = process.env.UPLOAD_SIZE_LIMIT

  // 執行期沒給就不比對: 直接 `next start` 是合法用法, 沒有第二個來源可以飄。
  if (!runtime || runtime === built) return

  console.error(
    `UPLOAD_SIZE_LIMIT 不一致：image 是以 ${built} 建置的，但執行期拿到 ${runtime}。`
    + " 這個值只能在 build 期決定，改了必須重新建置 image（make start）或發一版新的 tag。"
  )

  // `process.exit` 而不是 `throw`: Next 會接住 hook 拋出的錯誤並繼續監聽、對每個請求回 500。
  // 結束行程的話是明顯的重啟迴圈, nginx 等不到 web healthy, 不會有半套的服務上線。
  process.exit(1)
}

/**
 * Server Action 的加解密金鑰必須由執行期提供。
 *
 * image 裡的那一把是**公開常數** (見 `apps/web/Dockerfile`), 而 Next 在環境變數缺席時會
 * 退回用它 —— 忘了注入的下場是用全世界都知道的金鑰加密閉包參數, 而且沒有任何錯誤。
 * 跟 UPLOAD_SIZE_LIMIT 不同, 執行期沒給值也不放行: 這是安全性, 失敗要往「關」的方向倒。
 */
function requireActionsEncryptionKey() {
  if (process.env.NEXT_SERVER_ACTIONS_ENCRYPTION_KEY) return

  console.error(
    "缺少 NEXT_SERVER_ACTIONS_ENCRYPTION_KEY。image 裡只有公開的 id salt，"
    + " 沒有這個環境變數的話 Server Action 會用那把公開值加密閉包參數。"
    + " 用 compose 起的話它由 web 服務的 environment 注入（值在主機的 .env，make init 會產生）。"
  )
  // 理由同底下: throw 會被 Next 接住並讓伺服器繼續監聽。
  process.exit(1)
}
