# 模板的變更紀錄

**這份是模板的，下游專案不要寫進來** —— 下游自己的變更紀錄在
[`CHANGELOG.md`](CHANGELOG.md)。兩份分開是為了讓
`git diff HEAD template/main -- CHANGELOG.template.md` 只剩單向的上游條目；
合在一起的話，同一個區塊有兩個 owner，每次同步都衝突，而那份 diff 也不再讀得出
「我落後多少」。同步的作法見 [`docs/downstream.md`](docs/downstream.md#拉模板的更新)。

模板的實質改動記在這裡，版本對應 `apps/api/app/config.py` 的 `APP_VERSION`
（**那個版號在下游會被下游自己的產品版號取代**，見 `downstream.md`）。

每一筆條目開頭都要有同步影響標記，下游用它挑出真的要處理的部分：

| 標記 | 意思 |
|---|---|
| `[同步:無]` | 拉下來就好，不用做任何事 |
| `[同步:要動手]` | 同步後要改自己的東西，條目裡要寫清楚改什麼 |
| `[同步:破壞性]` | 不照做會壞掉（資料、部署或編譯） |

條目怎麼寫與 `## [Unreleased]` 的用法見
[`docs/development.md`](docs/development.md#changelog-條目)，
發版步驟見 [`docs/operations.md`](docs/operations.md#發版與回滾)。

## [Unreleased]

### 變更

- **[同步:要動手]** CI 重新分配各階段跑哪些 job。以「一次 draft push + Ready + merge」計，
  帳單從約 34 分鐘降到約 19 分鐘（實測值，不含 `publish`）：
  - **merge 到 `main` 只跑 `pushed-via-pr` 與 `publish`**，測試那六個 job 全部跳過。
    **這一條的前提是匯入 `.github/rulesets/main.json`**（strict：分支必須是最新才能
    merge，PR head 的 tree 才等於 merge 後的 tree）。**下游同步後要做的就是這件事** ——
    沒有匯入 ruleset 的話，把那六個 job 的 `if` 改回 `github.event_name != 'schedule'`。
  - `changelog`、`acceptance`、`test-edits` 三個 job 合併成 `pr-checks`（三個 step）。
    GitHub 逐 job 進位到整分鐘計費，三支各跑 4～6 秒卻各收一分鐘。
    **ruleset 的 required check 也跟著換成 `pr-checks`**，`make check-ci` 在守。
  - `security` 在 draft 期間不跑：它查的外部資料庫一天最多變一次，
    而 Ready 與每週一的 cron 已經是兩個落點。
  - tag build 完全不受影響，照跑全套 —— 那份 image 就是要上線的東西。
- **[同步:無]** dependabot 的三個基底映像 entry 從 monthly 改回 weekly。
  當初改 monthly 的理由是計費，而那個理由已經被上面那條與「repo 轉 public」拿掉了。
  下游是 private 而且分鐘數吃緊的話，改回 monthly 是一行的事，見
  [`docs/downstream.md`](docs/downstream.md#actions-分鐘數與-dependabot)。

- **[同步:要動手]** 模板與下游的變更紀錄分家：模板的搬到
  `CHANGELOG.template.md`，根目錄的 [`CHANGELOG.md`](CHANGELOG.md) 從此**屬於下游**。
  已經在用的下游同步這一筆時：把 `CHANGELOG.md` 裡自己寫的條目留著（合併衝突時選自己那邊），
  上游的條目一律以 `CHANGELOG.template.md` 為準。條目新增的同步影響標記由
  `make check-version` 擋，比對落後多少改用 `make sync`。
- **[同步:無]** 新增 `make sync`：抓模板、只把「要動手／破壞性」的條目挑出來、
  顯示 `apps/`／`scripts/`／`infra/` 的改動範圍，確認後才合併。
  模板自己跑它會直接說「這裡沒有 template remote」。
- **[同步:無]** CI 依 PR 階段分配工作量，把每月的 Actions 分鐘數從約 1550 壓到約 870
  （免費私有 repo 的額度是 2000）。紅綠燈出現的時機變了：
  - `deploy-config` 與 `e2e` 在 draft 期間不跑，按下 Ready for review 時補跑。
    draft 期間要看這兩盞燈就自己跑 `make check-compose` 與 `make e2e`。
  - 按下 Ready 時其餘 job 照樣重跑。**試過不重跑，會讓 PR 頁面說謊** ——
    被跳過的 job 仍然會產生一筆 `skipped` 的 check run 蓋掉 draft 期間那筆 `success`，
    而 `skipped` 對必要檢查算通過。實測結果寫在 `ci.yml` 的 `api` job 註解上。
  - 每週一的排程只跑 `security` —— 那本來就是那條 cron 唯一的存在理由。
  - 開 draft PR 的空 commit 建議帶 `[skip ci]`，見
    [`docs/development.md`](docs/development.md#落點要在動手之前存在)。
- **[同步:無]** [`docs/downstream.md`](docs/downstream.md) 新增〈Actions 分鐘數與 dependabot〉：
  免費方案的 2000 分鐘是**每個帳號**共用的，下游可以刪掉模板擁有的那四組 dependabot
  entry（兩個 docker、compose、github-actions），靠同步帶更新；`uv` 與兩個 `npm`
  不能全刪，因為下游會裝自己的相依。
- **[同步:無]** dependabot 的三個 base image entry（兩個 Dockerfile、一組 compose）
  從 weekly 改成 monthly；`uv` 與兩個 `npm` 維持 weekly。**代價**：OS 層的 CVE 修補最多
  延後一個月，而 `make audit` 掃不到那一層，期間不會有任何紅燈。理由與改回去的條件寫在
  [`.github/dependabot.yml`](.github/dependabot.yml) 的基底映像那一段。

## [0.0.1] - 2026-08-29

初始專案模板。功能概覽見 [`README.md`](README.md)，開案步驟見 [`TEMPLATE.md`](TEMPLATE.md)。
