import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // 產出物，不是我們寫的程式碼
    "coverage/**",
    "shared/api/generated/schema.d.ts",
  ]),
  {
    // 風格規則（owner 文件：docs/development.md 第 6 節）。
    //
    // 用 ESLint 核心的 max-len 而不是 @stylistic：只為一條規則多一個相依套件不划算。
    // 這幾條在 ESLint 9 標記為 deprecated，v10 移除時會是明確的設定錯誤而不是安靜失效，
    // 屆時再換 @stylistic 即可。
    //
    // **注意 ESLint 目前卡在 9.x，卡點不是這些規則**：`eslint-config-next` 帶進來的
    // `eslint-plugin-react` 最新版（7.37.5）peer 只到 `^9.7`，實測裝上 ESLint 10 會在
    // 載入 `react/display-name` 時就炸（`context.getFilename is not a function` ——
    // v10 移除了那組 deprecated context API）。等 eslint-plugin-react 支援 v10
    // （`npm view eslint-plugin-react peerDependencies`）之後才有得升，那時再一併換規則。
    rules: {
      // 後端是 ruff 的 line-length = 100，但兩者的「100」不同：ruff 算**顯示寬度**
      // （中文一字 2 欄），這裡算**字元數**（中文一字 1）。差異的取捨見 owner 文件。
      //
      // 豁免字串與 URL：i18n 的英文譯文本來就長，硬折成串接只會多出雜訊而不會更好讀。
      "max-len": ["error", {
        code: 100,
        ignoreStrings: true,
        ignoreTemplateLiterals: true,
        ignoreUrls: true,
        ignoreRegExpLiterals: true,
      }],
      // 以下三條是**防退步的地板**，不是重構目標（理由見 docs/development.md）。
      // 訂在現況之上留一格，所以開啟當下多數是 0 violation。
      "max-depth": ["error", 4],
      complexity: ["error", 10],
      "max-lines-per-function": ["error", { max: 60, skipBlankLines: true, skipComments: true }],
    },
  },
  {
    // 含 JSX 的檔案放寬 complexity 與函式長度。
    //
    // 不是「畫面可以比較亂」，而是這兩個指標對 JSX 失真：條件渲染的 `&&` 與三元運算
    // 每一個都計進 cyclomatic complexity，一個只是「有幾個欄位可能不顯示」的元件就會
    // 衝到十幾；JSX 本身也讓一個元件輕易破百行，而那些行不是邏輯。
    // 以副檔名切而不是列舉目錄：失真的來源是 JSX，不是它住在哪一層。
    //
    // 真正的畫面複雜度由別的機制擋：有分支的邏輯要抽進 capabilities.ts（有測試），
    // 跨模組共用的抽進 shared/ui。
    files: ["**/*.tsx"],
    rules: {
      complexity: ["error", 15],
      "max-lines-per-function": ["error", { max: 100, skipBlankLines: true, skipComments: true }],
    },
  },
  {
    // 測試檔不受函式長度限制。`describe(...)` 的回呼是**分組**而不是一個有邏輯的函式，
    // 把它算成「超長函式」只會逼人把相關的 `it` 拆散到不相干的 describe 裡，那讓測試更難讀。
    // complexity 仍然套用 —— 測試裡出現分支才是真的該警覺的事。
    files: ["tests/**"],
    rules: {
      "max-lines-per-function": "off",
    },
  },
]);

export default eslintConfig;
