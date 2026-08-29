import type { NextConfig } from "next";

// 型別從 `serverActions.bodySizeLimit` 衍生 —— 那是這個值**唯一**的消費者。
type ServerActionsConfig = NonNullable<NonNullable<NextConfig["experimental"]>["serverActions"]>;
type SizeLimit = NonNullable<ServerActionsConfig["bodySizeLimit"]>;

const uploadSizeLimitValue = process.env.UPLOAD_SIZE_LIMIT ?? "1mb";
if (!/^\d+(?:\.\d+)?(?:kb|mb|gb)$/i.test(uploadSizeLimitValue)) {
  throw new Error("UPLOAD_SIZE_LIMIT 必須使用容量格式，例如 500kb、1mb 或 1gb");
}
const uploadSizeLimit = uploadSizeLimitValue as SizeLimit;

const nextConfig: NextConfig = {
  output: "standalone",
  reactCompiler: true,
  devIndicators: false,
  // Server Action 參數可能含密碼；開發日誌只保留請求結果，不展開參數。
  logging: { serverFunctions: false },
  // Next 16.3 起 `next dev` 會自動在 app 根產生 AGENTS.md 與 CLAUDE.md。這個 repo 的 agent
  // 指引只有根目錄 AGENTS.md 一份本體，多一份自動生成的會變成沒人維護的第二來源。
  agentRules: false,
  experimental: {
    serverActions: {
      bodySizeLimit: uploadSizeLimit,
    },
  },
  // 這個區塊的值會在 build 時**內嵌成字面值**，所以裡面放的一律是「build 期的事實」而不是
  // 設定。部署設定請走 `shared/runtime/config.ts` 的執行期注入，理由寫在那裡。
  //
  // `BUILT_UPLOAD_SIZE_LIMIT` 是唯一一項，因為 `bodySizeLimit` 結構上移不到執行期：Next 把它
  // 序列化進 `.next/required-server-files.json`，standalone 的 server.js 讀那份檔案，不會重新
  // 求值本檔。把 build 當下的值留一份，`instrumentation.ts` 才能在開機時跟執行期的值比對。
  env: {
    BUILT_UPLOAD_SIZE_LIMIT: uploadSizeLimitValue,
  },
  // 這裡刻意**沒有** `/api/:path*` → 後端的 rewrite。用不到：資料存取一律走 Server Component
  // 與 Server Action（伺服器端直接打 `API_URL`），瀏覽器唯一還需要的後端路徑是 WebSocket 的
  // `/api/ws`，而那條由 nginx 自己的 location 處理。
  //
  // 留著的代價是 Next 這台對外伺服器變成通往內網 API 的**全域代理**，任何人都能透過它打到後端
  // 每一條路由。授權仍由後端的 permission dependency 擋，但那是最後一道防線，不該是唯一一道。
  //
  // **要在瀏覽器端呼叫後端時，不要把這條加回來** —— 在模組的 `actions.ts` 包一層具名的
  // Server Action（範例見 modules/push/actions.ts）。
};

export default nextConfig;
