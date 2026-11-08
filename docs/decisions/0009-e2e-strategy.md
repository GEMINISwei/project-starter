# 0009. E2E：CI 必跑正式環境 image，開發中用常駐的 dev 環境

狀態：採用（2026-11-08）

## 背景

E2E 要起整套 image 與 nginx，是 CI 最慢的一項，主流取捨是只在本機或排程跑。但 proxy 導向、cookie 屬性、
Server Action、權限導向、撤銷 session 只有整套跑起來才看得到。另一方面，開發中「先寫測試」至少紅綠各跑一次，
每次都建正式 image 跑整套就是好幾分鐘的空等。

## 決定

- CI 的 `e2e` 是 required check（`make check e2e`，正式環境 image）。只放跨層的 smoke 測試，畫面分支用 vitest。
- 部署沿用該 commit 在 `main` 上已成功的 CI，查不到才重跑；PR 上的 run 不算（測的不是 squash 後的 commit）。
- 開發中用 `make e2e`：每個 checkout 一套常駐 dev mode 環境（原始碼 bind mount），每次只跑指定的 spec。
  改到 nginx、compose 或只有正式環境才有的行為時，本機也跑 `make check e2e`。
- dev 與 build 都用 Turbopack，不加 `--webpack`（`apps/web/tests/package.test.ts` 擋）。下游專案實測
  dev 整套從約 5.2 分鐘降到約 2.8 分鐘、CPU 時間減半，webpack 首次編譯造成的逾時消失；build 跟著換，
  dev 與正式環境才不會多差一層打包工具。

## 後果

- 每個 PR 多等 E2E，換到登入、導向、cookie 這類壞了也不報錯的行為一定被跑過。
- 回滾到舊 tag 時沿用的是當時那份 CI 的結果。
- 不開 retries：偶發失敗要修等待條件，不能靠重跑。
- dev 與正式 build 的差異要到 CI 才發現，晚但不會漏。常駐環境佔資源，PR 合併後要 `make e2e down`。
- E2E 拖慢合併時先縮範圍或平行化，不移出 required checks；本機綠 CI 紅經常是 dev 差異造成時，
  把差異收進 overlay 或改回本機也跑正式版本。
