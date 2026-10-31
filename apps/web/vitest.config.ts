import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": import.meta.dirname,
      // 正式環境由 Next 在 build 時擋下「client 引用 server-only 檔」; 測試環境換成空模組。
      "server-only": `${import.meta.dirname}/tests/stubs/server-only.ts`,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    // 測試集中在 `tests/`, 與原始碼同構 (同後端的 `testpaths = ["tests"]`)。
    // 明寫 include 而不是用 vitest 預設的全域掃描: 預設會撿走任何位置的 `*.test.ts`,
    // 那等於「放哪都會跑」, 同構就不再是規則而只是習慣。
    include: ["tests/**/*.test.{ts,tsx}"],
    setupFiles: "./tests/setup.ts",
    coverage: {
      provider: "v8",
      // 終端只印摘要: 逐檔的表格連目錄小計一起印, 每跑一次 make check 就是一大段要讀進 AI 上下文的輸出。
      // 門檻沒過時照樣報錯; 要看哪幾行沒測到, 開 coverage/index.html。
      reporter: ["text-summary", "html"],
      // 只統計「有邏輯」的程式碼。兩類**刻意**不列進來 (是取捨, 不是遺漏):
      // - `modules/*/actions.ts`: 帶 `"use server"` 的薄包裝。會出錯的是 URL 與 payload 形狀,
      //   而那兩者由 OpenAPI 產生的型別在編譯期就擋掉了, 寫執行期測試只是在測 mock。
      // - `modules/*/ui/*.tsx`: 畫面組裝。有價值的分支已抽進 `capabilities.ts` 與 `shared/ui`。
      include: [
        "proxy.ts",
        "shared/**/*.{ts,tsx}",
        "modules/**/capabilities.ts",
      ],
      // `.server` 檔一樣算進來: `server-only` 在測試裡換成空模組 (上面的 alias), Next 的請求上下文
      // (cookies、headers、redirect) 用 `vi.mock` 換掉即可, 例見 tests/shared/api/request.server.test.ts。
      //
      // 刻意排除的只有 `"use server"` 的薄包裝: 與 `modules/*/actions.ts` 同一個理由 (會出錯的是
      // URL 與 payload 形狀, 型別已經擋了)。檔名看不出它是 action, 所以逐一列出。
      exclude: [
        "**/*.d.ts",
        "shared/i18n/actions.ts",
      ],
      // 防退步的地板, 不是目標。訂法: 量出現況 (納入 `.server` 檔之後: lines 91.4、statements 90.7、
      // functions 87.6、branches 82.3), 再往下留約 3 個百分點 —— 那個餘裕是量出來的, 拿掉一支
      // 測試檔就該讓它紅, 留太寬鬆的話那種退步照樣綠燈。
      //
      // branches 明顯低於其他三項是正常的: coverage-v8 會數到 JSX 條件渲染的每一個 `&&` 與
      // 三元, 而畫面分支刻意不寫執行期測試 (見上面的 include)。
      thresholds: {
        lines: 89,
        statements: 88,
        functions: 85,
        branches: 79,
      },
    },
  },
})
