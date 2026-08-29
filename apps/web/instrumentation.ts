/**
 * Next 的啟動掛勾（每個伺服器行程啟動時跑一次）。唯一的用途：擋掉「image 裡烤的設定」與
 * 「主機 .env 給的設定」不一致。
 *
 * `UPLOAD_SIZE_LIMIT` 是整包設定裡唯一結構上移不到執行期的一個（機制見 next.config.ts 的
 * `env` 區塊）。registry 模式下 image 由 CI 建、主機只是 pull，所以「改了主機的 .env 卻沒重新
 * 發版」真的會發生，而且**完全沒有症狀** —— 服務照常啟動，只有超過舊上限的上傳會拿到一個
 * 看起來莫名其妙的錯誤。
 *
 * 只在 Node.js runtime 跑：edge runtime 沒有這些環境變數，也不負責 Server Action body。
 */
export async function register() {
  if (process.env.NEXT_RUNTIME !== "nodejs") return

  const built = process.env.BUILT_UPLOAD_SIZE_LIMIT
  const runtime = process.env.UPLOAD_SIZE_LIMIT

  // 執行期沒給就不比對：直接跑 `next start`（沒經過 compose）是合法的用法，
  // 那時候只有 build 期的值，沒有第二個來源可以飄。
  if (!runtime || runtime === built) return

  console.error(
    `UPLOAD_SIZE_LIMIT 不一致：image 是以 ${built} 建置的，但執行期拿到 ${runtime}。`
    + " 這個值只能在 build 期決定，改了必須重新建置 image（make prod）或發一版新的 tag。"
  )

  // `process.exit` 而不是 `throw`：實測 Next 會把 instrumentation hook 拋出的錯誤接住，然後
  // **讓伺服器繼續監聽**並對每個請求回 500 —— 等於把「設定不一致」的可見度外包給 compose 那份
  // healthcheck 還在不在。直接結束行程就沒有這個前提，不管怎麼跑這個 image 失敗方式都一樣。
  //
  // 退出碼 1 配上 compose 的 `restart: always` 是明顯的重啟迴圈，而 nginx 等不到 web healthy
  // 也不會起來 —— 部署停在這裡，不會有半套的服務上線。
  process.exit(1)
}
