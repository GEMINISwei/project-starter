import react from "@vitejs/plugin-react"
import { defineConfig } from "vitest/config"

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": import.meta.dirname,
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    // 測試集中在 `tests/`，與原始碼同構（同後端的 `testpaths = ["tests"]`）。
    // 明寫 include 而不是用 vitest 預設的全域掃描：預設會撿走任何位置的 `*.test.ts`，
    // 那等於「放哪都會跑」，同構就不再是規則而只是習慣。
    include: ["tests/**/*.test.{ts,tsx}"],
    setupFiles: "./tests/setup.ts",
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      // 只統計「有邏輯」的程式碼。兩類**刻意**不列進來（是取捨，不是遺漏）：
      // - `modules/*/actions.ts`：帶 `"use server"` 的薄包裝。會出錯的是 URL 與 payload 形狀，
      //   而那兩者由 OpenAPI 產生的型別在編譯期就擋掉了，寫執行期測試只是在測 mock。
      // - `modules/*/ui/*.tsx`：畫面組裝。有價值的分支已抽進 `capabilities.ts` 與 `shared/ui`。
      include: [
        "proxy.ts",
        "shared/**/*.{ts,tsx}",
        "modules/**/capabilities.ts",
        "modules/push/client.ts",
        "modules/push/encoding.ts",
      ],
      // 排除判準：**能不能在 jsdom 載入**。帶 `server-only`（含傳遞性 import）的檔案在測試環境
      // 會直接拋錯，永遠測不到，留在分母裡只會稀釋數字。新增這類模組時記得一併加進來。
      //
      // 注意 `*.server.*` 這個命名慣例**抓不到帶 `"use server"` 的 action 檔** —— 它們同樣載不進
      // jsdom，但檔名不符合上面兩條 glob，所以要逐一列出。
      exclude: [
        "**/*.d.ts",
        "**/*.server.ts",
        "**/*.server.tsx",
        "shared/i18n/actions.ts",
      ],
      // 防退步的地板，不是目標。訂法：量出現況（lines 93.0、statements 91.9、functions 89.1、
      // branches 75.7），再往下留 3 個百分點 —— 那個餘裕是量出來的，拿掉一支測試檔（分頁那
      // 8 個 case）會讓 lines 掉到 88.2、branches 掉到 70.8，留太寬鬆那種退步照樣綠燈。
      //
      // branches 明顯低於其他三項是正常的：coverage-v8 會數到 JSX 條件渲染的每一個 `&&` 與
      // 三元，而畫面分支刻意不寫執行期測試（見上面的 include）。
      thresholds: {
        lines: 89,
        statements: 88,
        functions: 84,
        branches: 71,
      },
    },
  },
})
