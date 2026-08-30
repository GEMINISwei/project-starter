import type { KnipConfig } from "knip"

/**
 * 未使用的檔案、匯出與相依套件的靜態檢查。
 *
 * 用 `.ts` 而不是 `knip.json`：每一條例外都要寫得出理由，而 JSON 放不了註解。
 *
 * **entry 的訂法**：不要逐條列個別的忽略，而是把架構文件已定義的**公開面**當成進入點
 * （見 docs/architecture.md 的強制依賴規則 3 與 8）。那些 export 的存在不需要「repo 內部有人
 * 用」來證成 —— 下游專案才是使用者。
 */
const config: KnipConfig = {
  entry: [
    // Next.js 的路由慣例檔。proxy.ts 由 knip 的 Next 外掛自動認出，不必列。
    "app/**/{page,layout,loading,error,not-found,global-error,manifest}.{ts,tsx}",
    // 測試是進入點：它們沒有人 import，但正是它們在使用被測的東西。
    "tests/**/*.{ts,tsx}",
    // 模組的公開面與 manifest（依賴規則 3）。
    "modules/*/public.server.ts",
    "modules/*/public.client.ts",
    "modules/*/manifest.ts",
    // UI kit 的唯一入口（依賴規則 8）。一個 kit 有目前沒人用的元件是正常的。
    "shared/ui/index.ts",
    // 契約型別的具名目錄，用途就是給人按名字引用 —— 即使某些型別目前都由 url 自動推導。
    "shared/api/entities.ts",
    // 模組啟用清單。`ENABLED_MODULES` 與 `getRoute` 是新增模組時要改／要用的擴充點，
    // 見 docs/extending.md 的〈新增前端頁面〉。
    "config/routes.ts",
    // service worker 由瀏覽器在執行期抓取，沒有任何 import 指向它。
    "public/sw.js",
  ],
  project: ["**/*.{ts,tsx}"],
  // `make gen-types` 直接跑 npx，刻意不寫進 package.json 的 scripts
  //（理由見 package.json 的 `//scripts`），所以靜態分析看不到它被使用。
  ignoreDependencies: ["openapi-typescript"],
  // 型別只在自己檔案裡用到仍可以 export：那是「給這個模組的回傳值一個名字」，
  // 不是死碼。值就不一樣了 —— 只在自己檔案裡用到的函式或常數不該對外。
  ignoreExportsUsedInFile: { type: true, interface: true },
  // 用 tag 而不是 `ignore: [檔案]`：整檔忽略的範圍比理由大太多 —— 同一個檔案裡有人在用的
  // `createCookies` / `deleteCookies` 會一起被豁免，哪天失去最後一個呼叫端 knip 不會出聲。
  // 只有標了 `@knipignore` 的那個 export 豁免，理由寫在它自己的 JSDoc 上。
  tags: ["-knipignore"],
}

export default config
