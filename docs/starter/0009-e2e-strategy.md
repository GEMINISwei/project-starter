# 0009. E2E：CI 必跑正式環境 image，開發中用常駐的 dev 環境

指令與分份的調整方式見 [`testing.md`](../testing.md#e2ee2e)。

## 決定

- CI 的 `e2e` 是合併條件（`make check e2e`，正式環境 image；由 required check `ci-gate` 納入，只改 Markdown 的 PR 才跳過）。
  只放跨層的 smoke 測試，畫面分支用 vitest。
- 部署沿用該 commit 在 `main` 上已成功的 CI，查不到才重跑；PR 上的 run 不算（測的不是 squash 後的 commit）。
- 開發中用 `make e2e`：每個 checkout 一套常駐 dev mode 環境（原始碼 bind mount），每次只跑指定的 spec。
  正式環境的完整版本由 CI 跑，本機不必先跑 `make check e2e`。
- dev 與 build 都用 Turbopack，不加 `--webpack`（`apps/web/tests/package.test.ts` 擋）。
- CI 的 `e2e` 依檔案分份（matrix 加 Playwright `--shard`），**每份各起一套環境**，不在同一套加 worker。
- 不開 retries：偶發失敗要修等待條件，不能靠重跑。

## 為什麼

E2E 要起整套 image 與 nginx，是 CI 最慢的一項，主流取捨是只在本機或排程跑。但 proxy 導向、cookie 屬性、
Server Action、權限導向、撤銷 session 只有整套跑起來才看得到，壞了也不會報錯，所以每個 PR 都要跑過。

開發中「先寫測試」至少紅綠各跑一次，每次都建正式 image 跑整套就是好幾分鐘的空等，所以本機用常駐的 dev 環境，
只跑相關的 spec。

dev 用 Turbopack，整套 E2E 的時間與 CPU 大約是 webpack 的一半，也不會因為首次編譯太久而逾時；build 用同一套，
dev 與正式環境才不會多差一層打包工具。

分份而不加 worker：runner 同時要跑整套服務，2 個 worker 已是 CPU 的上限；同一 IP 的登入有上限、成功也不歸零，
worker 一多會碰到限流。

不採用的做法：

- 依改動挑 spec：跨層行為對不到單一模組，漏跑的會直接進 `main`，部署又沿用 `main` 的結果。
- 每個功能一個 job：大小不一，最大的拖住整體，清單還要跟著維護。
- 合併報告的 job：`ci-gate` 要等它，平時又多一段時間；每份失敗時各自上傳 `playwright-report-<份號>` 就夠了。

## 代價

- 每個 PR 都要等 E2E。
- 回滾到舊 tag 時沿用的是當時那份 CI 的結果。
- dev 與正式 build 的差異要到 CI 才發現，晚但不會漏。
- 常駐環境佔資源，PR 合併後要 `make e2e down`。

## 什麼時候重新檢討

- E2E 拖慢合併時，先縮範圍或平行化，不移出合併條件。
- 本機綠、CI 紅經常是 dev 差異造成時，把差異收進 overlay，或改成本機也跑正式版本。
