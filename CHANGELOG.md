# 變更紀錄

模板的實質改動記在這裡，每一筆都寫明**下游同步時需要做什麼**。版本對應
`apps/api/app/config.py` 的 `APP_VERSION`。

條目怎麼寫與 `## [Unreleased]` 的用法見
[`docs/development.md`](docs/development.md#changelog-條目)，
發版步驟見 [`docs/operations.md`](docs/operations.md#發版與回滾)。

## [Unreleased]

### 變更

- CI 依 PR 階段分配工作量，把每月的 Actions 分鐘數從約 1550 壓到約 870
  （免費私有 repo 的額度是 2000）。**下游同步時不需要做任何事**，
  但值得知道紅綠燈出現的時機變了：
  - `deploy-config` 與 `e2e` 在 draft 期間不跑，按下 Ready for review 時補跑。
    draft 期間要看這兩盞燈就自己跑 `make check-compose` 與 `make e2e`。
  - 按下 Ready 時其餘 job 照樣重跑。**試過不重跑，會讓 PR 頁面說謊** ——
    被跳過的 job 仍然會產生一筆 `skipped` 的 check run 蓋掉 draft 期間那筆 `success`，
    而 `skipped` 對必要檢查算通過。實測結果寫在 `ci.yml` 的 `api` job 註解上。
  - 每週一的排程只跑 `security` —— 那本來就是那條 cron 唯一的存在理由。
  - 開 draft PR 的空 commit 建議帶 `[skip ci]`，見
    [`docs/development.md`](docs/development.md#落點要在動手之前存在)。
- [`docs/downstream.md`](docs/downstream.md) 新增〈Actions 分鐘數與 dependabot〉：
  免費方案的 2000 分鐘是**每個帳號**共用的，下游可以刪掉模板擁有的那四組 dependabot
  entry（兩個 docker、compose、github-actions），靠同步帶更新；`uv` 與兩個 `npm`
  不能全刪，因為下游會裝自己的相依。
- dependabot 的三個 base image entry（兩個 Dockerfile、一組 compose）從 weekly 改成
  monthly；`uv` 與兩個 `npm` 維持 weekly。**代價**：OS 層的 CVE 修補最多延後一個月，
  而 `make audit` 掃不到那一層，期間不會有任何紅燈。理由與改回去的條件寫在
  [`.github/dependabot.yml`](.github/dependabot.yml) 的基底映像那一段。

## [0.0.1] - 2026-08-29

初始專案模板。功能概覽見 [`README.md`](README.md)，開案步驟見 [`TEMPLATE.md`](TEMPLATE.md)。
