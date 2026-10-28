# 更換視覺／導入 Design System

設計變數的**名字與預設值**在 `apps/web/shared/ui/styles/tokens.css`，那是 UI kit 與各模組 CSS
module 共用的契約，跟著 shared 走。**這個專案的外觀在 `apps/web/app/theme.css` 覆寫**：只寫要改的
那幾個變數，名字不要自創。導入 Design System 時把 theme.css 的右手邊改成 DS 的值或變數即可。
需要新的變數時先加進 tokens.css（給預設值），再在 theme.css 覆寫。底色改了要同步
`apps/web/app/manifest.ts` 的 `theme_color`。
