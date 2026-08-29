// 不要加上 `server-only`：這是純函式，抽出來就是為了能被單元測試。碰到 next/headers
// 的那一步留在呼叫端（modules/auth/actions.ts）。

/**
 * 依 `X-Forwarded-Proto` 決定 cookie 要不要帶 `Secure`。
 *
 * 判斷跟著實際連線協定走，不是建置期的 `NODE_ENV`：HTTP 部署自動不加、前面接上 TLS
 * 就自動加回來，不需要改 .env。nginx 的兩份設定都已在 `location /` 送出這個 header，
 * 且是覆寫（`$scheme`）而非沿用用戶端送來的值，所以偽造不了。
 *
 * **在 nginx 前面再加一層 proxy（CDN、ALB…）時，那一層必須照樣送 `X-Forwarded-Proto`**，
 * 否則讀不到 header 會回傳 false，HTTPS 部署就悄悄退化成非 Secure cookie。
 */
export function resolveCookieSecure(forwardedProto: string | null | undefined): boolean {
  // 多層 proxy 會把值串成 `"https, http"`；第一段才是面對用戶端的那一層。
  return forwardedProto?.split(",")[0]?.trim().toLowerCase() === "https"
}
