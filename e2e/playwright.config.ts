import { defineConfig } from "@playwright/test"

/**
 * bootstrap 之後的登入狀態。其餘 spec 靠它省掉重複登入 ——
 * **而且非省不可**：建立第一個超級管理者一個部署只能成功一次，
 * 每支 spec 各做一次的話第二支就會失敗。
 */
export const STORAGE_STATE = "./.auth/admin.json"

/**
 * 「看著它跑」模式：`E2E_HEADED=1 make e2e` 開一個真的 Chromium 視窗，
 * 並把每個動作放慢到人眼跟得上。它買到的是**看**，不是**測** —— 斷言一條都沒變。
 *
 * **一律讀環境變數，不要讀 `process.argv`。** playwright 的 worker 是另一個行程、
 * 會再載一次這個檔案，那裡的 argv 沒有 CLI 旗標 —— 靠 argv 判斷會讓主行程與 worker
 * 算出不同的 slowMo 與 timeout，而且完全不會有訊息。`scripts/e2e.sh` 因此把
 * `--headed` 翻成 E2E_HEADED 再傳進來。
 *
 * **CI 上一律忽略。** runner 沒有顯示器，headed 只會停在找不到 display 上超時，
 * 而那個錯誤訊息跟原因對不起來。這裡是忽略而不是像上面 forbidOnly 那樣直接紅燈，
 * 刻意的：`.only` 會讓 CI 對覆蓋率說謊，headed 不改變任何斷言 ——
 * 讓整個 job 為一個顯示偏好紅掉沒有意義。clamp 放在 config 而不是腳本裡，
 * 直接跑 `npx playwright test` 的人才也被涵蓋。
 */
const headed = Boolean(process.env.E2E_HEADED) && !process.env.CI

/**
 * 每個動作之間停多久（毫秒）。300 是「看得清楚在點哪裡」與「不必等到不耐煩」的折衷；
 * 要逐格看就 `E2E_SLOWMO=1000`，要全速的 headed 就 `E2E_SLOWMO=0`。
 *
 * 非數字時退回預設而不是照傳：`slowMo: NaN` 會讓瀏覽器整個不動，且不會有任何錯誤。
 */
const slowMoOverride = Number(process.env.E2E_SLOWMO)
const slowMo = Number.isFinite(slowMoOverride) ? slowMoOverride : headed ? 300 : 0

export default defineConfig({
  testDir: "./tests",
  // 全部串行。這幾支共用同一個資料庫，平行跑會互相看到對方建立的項目 ——
  // 而 e2e 的數量刻意很少（只測跨層接縫），平行化省不到什麼。
  workers: 1,
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  // **不重試**。e2e 不穩定時要修的是那個不穩定，不是把它重跑到綠 ——
  // 這一層的價值全部來自「它紅的時候真的有事」，retry 會把那個訊號洗掉。
  retries: 0,
  // **html 兩邊都要開**：CI 的 `github` reporter 只吐 PR 上的 inline annotation，
  // 它**不產生任何檔案** —— 只掛它的話 upload-artifact 會找不到東西可收，
  // 而那正好發生在你最需要看報告的時候。annotation 指出「哪一條失敗」，
  // html 報告才有 trace、截圖與每一步的細節。
  reporter: process.env.CI
    ? [["github"], ["html", { open: "never" }]]
    : [["list"], ["html", { open: "never" }]],
  // 這兩個數字是配著 **dev 模式**訂的，不是「斷言可以慢」。`next dev` 在第一次請求某條
  // 路由時才編譯它，而 scripts/e2e.sh 的暖機只能先編首頁與 /signup —— 需要登入才進得去的
  // /items 與 /settings，它們的第一次編譯還是落在測試裡面。
  // 抓太緊的症狀是「第一支跑到那條路由的測試 timeout，重跑就過」，而 retries 是 0。
  //
  // 上面那 90 秒**沒有含放慢**。slowMo 是加在**每一個動作**上的，一支測試有幾十個動作，
  // `E2E_SLOWMO=1000` 一個人就能吃光整個預算。不把它加進去的症狀是「headed 跑到一半
  // timeout，換回 headless 就過」—— 看起來像「被看著就會壞」，實際上是在量放慢本身。
  // 200 是單支測試的動作數上限（目前最長的 bootstrap 約 20 個），刻意留得很寬：
  // 這筆預算只在 headed 時存在，而 headed 本來就是給人看的，寬一點不花任何代價。
  // `E2E_SLOWMO=0` 時這一項是 0，行為與 headless 完全相同。
  timeout: 90_000 + slowMo * 200,
  // expect 這邊**不跟著放大**：它的重試是時間預算不是次數預算，slowMo 只讓同一段
  // 15 秒裡的重試次數變少，不會讓斷言本身需要更久。
  expect: { timeout: 15_000 },
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3100",
    headless: !headed,
    launchOptions: { slowMo },
    // 語系釘死，不要跟著跑測試那台機器的系統語言走 —— 其中一條接縫測的就是語系切換，
    // 起點浮動的話那條測試會時綠時紅，而原因完全看不出來。
    locale: "zh-TW",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "bootstrap",
      testMatch: /bootstrap\.setup\.ts/,
    },
    {
      name: "seams",
      testMatch: /.*\.spec\.ts/,
      dependencies: ["bootstrap"],
      use: { storageState: STORAGE_STATE },
    },
  ],
})
