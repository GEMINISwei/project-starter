# 變更紀錄

這個 repo 的實質改動記在這裡，版本對應 `apps/api/app/config.py` 的 `APP_VERSION`。

**用這個模板開出新專案時**：把底下的條目清空，從你自己的第一版重新開始寫
（`APP_VERSION` 也一起重設）。模板的歷史留在模板 repo 上，不需要跟著複製到每個專案。

條目怎麼寫與 `## [Unreleased]` 的用法見
[`docs/development.md`](docs/development.md#changelog-條目)，
發版步驟見 [`docs/operations.md`](docs/operations.md#發版與回滾)。

## [Unreleased]

### Fixed

- `scripts/deploy.sh` 的 smoke test 改成重試到通（最多 60 秒），不再打一次就定生死。
  `up -d` 在 nginx 的 depends_on 條件成立時就回來，那時 nginx 才剛 start，
  單發的 curl 會撞在它還沒 listen 的空隙上 —— 症狀是部署其實成功、卻被回報成失敗並觸發回滾。

### Changed

- `color-scheme`、狀態色與陰影顏色搬進主題介面。`color-scheme` 從 `app/tokens/semantic.css`
  移到每一份 `app/themes/*.css`；狀態色從 `--success-600`／`--success-100` 改名成
  `--color-success-fg`／`--color-success-bg`（warning／danger／info 同）並住進主題層；
  `--ds-shadow-*` 只留幾何與濃度，顏色改由主題的 `--color-shadow` 給。
  三者以前都在主題介面外面，換主題換不掉，而且漏掉沒有紅燈。**顏色的實際值不變。**
- `check-tokens.mjs` 多兩條規則：w（`color-scheme` 只能宣告在主題檔，且每份主題都要宣告）、
  x（`--ds-shadow-*` 不可自帶色值）。
- `tests/app/themes/contrast.test.ts` 多測狀態色的文字對它自己的底；
  它的宣告解析器現在會先剝掉註解 —— 註解裡示範用的宣告會吃掉後面的真宣告。

## [0.0.1] - 2026-08-29

初始專案模板。功能概覽見 [`README.md`](README.md)，開案步驟見 [`TEMPLATE.md`](TEMPLATE.md)。
