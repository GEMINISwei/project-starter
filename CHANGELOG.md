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
  - `api`／`web`／`api-types-up-to-date`／`changelog`／`test-edits` 在
    Ready for review 時**不重跑**（status check 掛在 commit SHA 上，按 Ready 不改變
    SHA）。`security` 是唯一的例外，它查的是會自己變紅的外部 advisory 資料庫。
  - 每週一的排程只跑 `security` —— 那本來就是那條 cron 唯一的存在理由。
  - 開 draft PR 的空 commit 建議帶 `[skip ci]`，見
    [`docs/development.md`](docs/development.md#落點要在動手之前存在)。
- dependabot 的三個 base image entry（兩個 Dockerfile、一組 compose）從 weekly 改成
  monthly；`uv` 與兩個 `npm` 維持 weekly。**代價**：OS 層的 CVE 修補最多延後一個月，
  而 `make audit` 掃不到那一層，期間不會有任何紅燈。理由與改回去的條件寫在
  [`.github/dependabot.yml`](.github/dependabot.yml) 的基底映像那一段。

## [0.0.1] - 2026-08-29

初始專案模板。功能概覽見 [`README.md`](README.md)，開案步驟見 [`TEMPLATE.md`](TEMPLATE.md)。
