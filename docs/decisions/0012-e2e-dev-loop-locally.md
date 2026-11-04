# 0012. 開發中的 E2E 用常駐的 dev 環境，正式環境 image 由 CI 驗證

狀態：採用（2026-11-03）

## 背景

`make check e2e` 每次都建正式環境的 image、起一套新的 stack、跑完整套再拆掉，CI 跑的就是它，
「本機綠，CI 就綠」。但開發中要的是改一點、跑相關的那幾個：先寫測試的流程至少要紅綠各跑一次，
每次都等建置與整套測試，一輪就是好幾分鐘。AI 協作時這段時間全是空等。

常見的做法是本機跑跟 CI 一模一樣的那份，差異最小。

## 決定

開發中用 `make e2e`：每個 checkout 一套常駐的 **dev mode** 環境（原始碼 bind mount，改了不必重建），
`make e2e test`／`grep` 每次先重設資料、重建超管、重啟 api，再只跑指定的 spec 或名稱。
正式環境 image 的完整版本只在 CI 的 `e2e` 跑（`make check e2e`）；改到 nginx、compose 或只有正式環境
才有的行為時，本機也跑一次 `make check e2e`。

## 後果

- 一輪從好幾分鐘變成十幾秒加上那幾個測試的時間。
- dev 與正式環境 build 的差異（Next 的 dev server 與 production build、dev 的 nginx 模板）要到 CI 才會發現，
  發現得晚，但不會漏，因為 CI 的 `e2e` 是必要檢查（[0011](0011-e2e-required-in-ci.md)）。
- `next dev` 第一次打開頁面時才編譯，第一次跑某個頁面的測試會比較慢；`make e2e up` 先載入登入頁，
  其餘頁面編譯過一次之後就快了。
- dev 與 build 都用 Next 預設的 Turbopack，不加 `--webpack`（`apps/web/tests/package.test.ts` 擋）。
  在一個 75 個 E2E 測試的下游專案實測（2 workers）：webpack 的 dev 整套 5.2–5.3 分鐘、約 1000 CPU 秒，
  第一輪有 4 個測試等頁面第一次編譯而逾時；Turbopack 2.6–2.9 分鐘、約 500 CPU 秒，冷、暖啟動都全過，
  單一 spec 從 31 秒降到約 12 秒。build 跟著換，是為了不讓 dev 與正式環境再多差一層打包工具。
  同一個下游專案已用 Turbopack 建的 image 部署到正式環境：web 沒有重啟、log 沒有 Edge Runtime 警告，
  路由保護、登入與 Server Action 的寫入都正常。
- 常駐環境會一直佔著資源，PR 合併後要 `make e2e down`（`watch-pr` 的收尾有這一步）。
- 本機綠、CI 紅經常是 dev 與正式環境的差異造成時，重新檢討：把差異收斂進 overlay，或改回本機也跑正式環境的版本。
