# 變更紀錄

這個 repo 的實質改動記在這裡，版本對應 `apps/api/app/config.py` 的 `APP_VERSION`。

**用這個模板開出新專案時**：把底下的條目清空，從你自己的第一版重新開始寫
（`APP_VERSION` 也一起重設）。模板的歷史留在模板 repo 上，不需要跟著複製到每個專案。

條目怎麼寫與 `## [Unreleased]` 的用法見
[`docs/development.md`](docs/development.md#changelog-條目)，
發版步驟見 [`docs/operations.md`](docs/operations.md#發版與回滾)。

## [Unreleased]

### 變更

- **更新 ruleset 的指令從 `POST` 改成 `PUT`（三處）。** `POST` 是「建立」不是「更新」——
  第一次匯入時它是對的，但改過 `main.json` 之後照著做，GitHub 會多出**第二個同名的
  `main` ruleset**（名稱不要求唯一），兩個都是 active、兩份規則疊加。症狀很惡劣：
  required checks 看起來是對的（新的那份確實有你剛加的 job），但舊的那份還在，
  之後想調鬆任何一條時會改到其中一個、另一個繼續擋著，**而且沒有任何地方會提示你有兩份**。
  三處裡 `scripts/check-ci.sh` 那行最關鍵 —— 它印出來的時機必定是「ruleset 剛被改過」，
  也就是唯一需要 `PUT` 的情境。`TEMPLATE.md` 的開案情境確實是首次匯入，`POST` 維持不動，
  只補一句指路。`docs/development.md` 的〈匯入 ruleset〉是這個主題的 owner，兩種都寫。

- **新增 `draft-gated-jobs` job，把「draft 期間跳過的三個 job 從來沒補跑過」從沉默變成紅燈。**
  `deploy-config`／`e2e`／`security` 在 draft 上跳過，靠 `ready_for_review` 事件補跑 ——
  而那個補跑會被 push 撞掉。實測到**兩種**成因不同、結果相同的壞法：PR #14 是兩個 run
  都建立、被 concurrency 互砍掉一個；PR #15 是第二個 run 壓根沒被建立。兩種都讓那三個
  停在 skipped，而 **skipped 對 required status check 算通過** —— PR 頁面是綠的，
  看不出它們從來沒跑過。
  因為成因不只一種，這裡不去修 race，改成**檢查結果**：PR 已經 ready 卻還有 skipped
  就紅燈，並告訴你推個空 commit 重新觸發。判斷用的是**當下**的 draft 狀態（`gh pr view`），
  不是事件 payload —— payload 記的是事件發生當時，讀它會跟著一起被騙過去。
  `.github/rulesets/main.json` 同步加入這個 context，**要重新匯入 GitHub 才生效**。

- **`ci.yml` 補上 `workflow_dispatch`。** 原本想「對現在的 `main` 重跑一次完整 CI」
  沒有入口 —— 只能 re-run 一個舊 run，而那跑的是舊 SHA，答不了那個問題
  （merge 那一輪刻意不重跑測試）。**六個測試 job 的 `if` 也一起放行**：它們原本只認
  `pull_request` 與 `tag`，只加 `on:` 的話手動觸發會得到一個「所有 job 都 skipped」的空 run，
  而那個畫面看起來像成功。`pr-checks` 刻意不放行（它讀 PR 標題與描述，手動觸發時沒有）。

- **新增 [`.github/SECURITY.md`](.github/SECURITY.md)。** repo 是 public，而回報漏洞原本
  沒有任何指定管道。它**刻意不寫人名或信箱**，走 GitHub 的 repo 相對入口，
  所以複製到下游之後回報會進到下游自己的 repo，不會誤送到模板維護者。
  代價是那個「Report a vulnerability」按鈕要開 repo 的 Private vulnerability reporting
  才會出現 —— 開關列進 `TEMPLATE.md` 第 5a 步（原本三件變四件）。

- **`publish` 為兩個 image 產生 build provenance attestation。** 補的是 `deploy.yml`
  信任鏈裡唯一一段靠推論撐著的地方：它等 CI 綠燈、篩 `event == push`，然後在主機上
  pull `sha-<short>` —— 但 tag 是可以被重指的，任何拿得到 `packages: write` 的東西都能
  覆蓋它，而覆蓋之後 CI 仍然是綠的。證明簽在 Sigstore 上，並以 OCI referrer 一起推回
  GHCR（離線或受限網路的主機才驗得到）；主體是 digest 不是 tag，所以一份涵蓋那次推出去的
  每一個 tag。驗證方式與「`deploy.sh` 還沒有自動跑它」寫在
  [`docs/operations.md`](docs/operations.md)。
  **`provenance: false` 沒有動** —— 那一行關的是 buildx 塞進 image manifest 的 inline
  provenance，跟這份存在 image 外面的證明是兩件事，原本的決定與敘述都還成立。

- **`make check-ci` 加上 actionlint。** 這支原本守的是「三處手抄的東西對不上」
  （CI 內嵌指令 vs. `scripts/`、ruleset vs. job 名單），而「這份 YAML 自己就寫錯了」
  沒有任何人在看 —— workflow 的錯誤幾乎都要推上去才會現形。走釘死版本的 docker image
  （Docker Desktop 本來就是前置需求，而 ubuntu runner 沒有內建 actionlint），
  本機與 CI 跑同一個版本。沒有 docker 時會明講跳過了什麼，不靜靜放行。
  導入時它報的三條都就地處理掉了，**沒有加 `.github/actionlint.yaml` 全域抑制**：
  `ci.yml` 的等待迴圈改用 `for _`、step summary 的五個 `>>` 收成一個區塊，
  `deploy.yml` 那條 jq 的誤報加了一行帶理由的 `# shellcheck disable`。

- `docs/downstream.md` 新增〈部署主機的架構要先決定〉。`operations.md` 早就寫了
  「只建 linux/amd64、arm64 主機拉得下來跑不起來」的症狀，缺的是**這個決定該在什麼時機做** ——
  選主機的時候，不是第一次部署失敗的時候。

- **清掉舊「可同步上游」模型的五處殘留，並移除 `make remote`。** 改成 GitHub template
  repository 之後，還有五個地方在描述已經不存在的模型，而檢查器全部抓不到（`check-docs`
  守的是路徑與錨點存在，守不到「這段文字描述的東西已經沒了」）：`README.md` 的
  Quickstart 教人把模板留成上游、`docs/development.md` 描述 `make remote` 對 `template`
  這個名稱的特殊行為（`remote.sh` 裡從來沒有那段邏輯）、`.githooks/pre-push` 的註解與
  **執行期訊息**都說下游靠 `git merge template/main` 同步、`TEMPLATE.md` 指向一個不存在的
  步驟。連帶：
  - 移除 `make remote` 與 `scripts/remote.sh`。快照模式下正常開案（"Use this template"
    之後 `git clone`）`origin` 早就綁好了，它一次都不會被呼叫；剩下的退路
    （下載 ZIP、`rm -rf .git`）用兩行標準 git 指令就夠。而它最複雜的那段
    （判斷共同祖先、警告 unrelated histories）本來就是為了舊模型寫的。
  - `TEMPLATE.md` 第 6 步從「順手 grep 一下」改成逐檔清單。**照原本的寫法走完清單會讓
    下游第一個 PR 紅燈** —— `git rm TEMPLATE.md` 之後有 12 條 markdown 連結斷掉，散在
    五個檔案，而 `check-docs` 在 CI 的 `deploy-config` job 裡。
  - `TEMPLATE.md` 的附錄補上「repo 的 `Template repository` 開關要打勾」。整個開案模式
    建立在它上面，而它跟 ruleset、secret scanning 一樣是 GitHub 那一側的設定 ——
    版控裡看不到，也沒有任何檢查器守得到。
  - `docs/downstream.md` 的標題層級改成四個主題各自 `##`（原本三個主題擠在 `CI/CD`
    底下當 `###`），並修掉兩處指反方向的「見上一節／下一節」。標題文字沒動，
    既有的錨點連結全部還有效。

- `make init` 問資料庫帳號時的預設值從 `admin` 改成 `app`，與 `.env.example` 和
  `docs/development.md` 的表格一致。`check-env` 比對的是變數名不是預設值，所以這三處
  飄了沒有任何症狀。

- **改用 GitHub template repository 模式，不再提供可同步的上游。** 新專案用
  "Use this template" 開出來，拿到的是一份快照：沒有共同歷史、沒有 `template` remote、
  之後也不會有同步。**所以新專案可以改任何地方**，包含 `shared/` 與組裝層。
  取捨與理由寫在 [`TEMPLATE.md`](TEMPLATE.md) 的第 0 節（一句話：可同步的上游要成立，
  前提是每個專案都遵守「不要改 `shared/` 與組裝層」，而多個平行開發的專案幾乎必然破壞它；
  破壞之後就是付了成本卻拿不到好處）。連帶：
  - 移除 `make sync` 與 `scripts/sync.sh`。
  - 移除 CHANGELOG 條目的同步影響標記與 `make check-version` 對它的檢查。
  - `docs/downstream.md` 從「同步紀律」改寫成「開案後指南」，只留開案後真的要做的決定
    （CI/CD 留哪些、安全掃描、Actions 分鐘數、移除 CD）。
  - `AGENTS.md` 移除「有 `template` remote 就不要改 `shared/`」那條規則。
  - **變更紀錄維持單一份 `CHANGELOG.md`。** 開發過程中一度拆成
    `CHANGELOG.template.md` 加一份種子檔，那是為了讓「模板與下游持續寫進同一條血脈」
    不會永遠衝突而設計的；快照模式下同一時間只有一個 owner，拆開就只剩成本。
    連帶 `make check-version` 不再需要判斷「這個 repo 是模板還是新專案」，
    CI 的 CHANGELOG 守衛也從兩個方向縮回一個（只擋漏寫）。

- `NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` 不再被烤進 web image。
  這把金鑰在 Next 裡同時扛兩個需求相反的角色 —— build 期是 Server Action id 的 salt
  （要穩定、不必保密），執行期是閉包參數的加解密金鑰（要保密、要能輪替）。綁在同一個值上的
  結果是**秘密被寫進建置產物**：`.next/server/server-reference-manifest.json` 跟著 image 走，
  任何拿得到 image 的人都讀得出正式環境的金鑰。現在 build 期用一個寫死的公開常數，
  真金鑰由 compose 在執行期注入，忘了注入由 `apps/web/instrumentation.ts` 在開機時擋下來。
  理由、四個實測結果與「為什麼不是隨機值」寫在
  [`apps/web/Dockerfile`](apps/web/Dockerfile) 的長註解。

  **從舊版模板開出來的專案，要自己搬這個修正的話，還要做三件事**：

  1. **刪掉 GitHub 的 repository secret `NEXT_SERVER_ACTIONS_ENCRYPTION_KEY`** ——
     已經沒有任何 job 需要它（`publish` 那一步的存在性檢查也一併刪了）。
  2. **如果你的 GHCR package 曾經是 public**，那些 image 裡有你的正式金鑰：
     改回 private，並在主機 `.env` 換一把新的（`openssl rand -base64 32`）後重啟。
  3. 下一次部署會讓所有 Server Action id 改變一次（salt 換了），使用者開著沒重載的分頁
     按下按鈕會拿到「Server Action ... was not found on the server」，重載即可。
     這是一次性的。

  主機 `.env` 不用動（`make init` 本來就會產生這個值），但 compose 現在用 `${VAR:?}` 要求它
  存在 —— 手寫過 `.env` 的話先確認那一行還在。

  CI 的 `deploy-config` 多一步「確認 web image 沒有把金鑰烤進去」，斷言 image 裡的
  `encryptionKey` 就是 Dockerfile 那個公開常數。**不用通用的 secret 掃描器是有實測依據的**：
  trivy 的 secret scanner 對真的含金鑰的舊 image 掃出 0 筆，對只含那份 manifest 的對照組
  也是 0 筆 —— 它不認「JSON 欄位裡的一串 base64」，加了會得到一個守不到的檢查。

- 模板的預設立場改成「repo 是 public」。免費方案上 public 與 private
  拿到的東西差很多（Actions 分鐘數、ruleset、secret scanning、CodeQL、environment 的
  required reviewers 五項），原本散在各處的「這是付費功能所以不預設」全部重寫。
  **開新專案時**照 [`TEMPLATE.md`](TEMPLATE.md) 的第 5a 步把 repo 設成 public 並跑那三件設定；
  **維持 private 的話** [`docs/downstream.md`](docs/downstream.md) 每一節都寫了對應的作法。
  - **`ruleset` 從「選配」變成「開案必做」**：`ci.yml` 讓 merge 到 `main` 那一輪不重跑測試，
    前提就是它的 strict 政策 —— 沒匯入的話那個洞**沒有任何症狀**。
  - `deploy-config` 與 `e2e` 在 draft 期間跳過的理由從「計費」改成「回饋速度」。
    行為沒變，但理由變了：public 之後分鐘數無限，留著舊理由會讓人以為可以全開回去。
  - 新增警告：**public repo 不能掛 self-hosted runner**（fork PR 可以在你的機器上
    執行任意程式碼）。
  - public repo 的部署主機可以匿名 `git fetch`，deploy key 那段只有 private 需要。
- `ci.yml` 裡三個寫死的假金鑰改成每次執行時現產（`openssl rand -base64 32`）。
  值本來就是假的（解開來是 `ci-only-not-a-real-key-32bytes!!`），但泛型的 secret 掃描器
  只看熵，照樣判成外洩並寄信 —— 而那串字會被**每一個下游繼承**，等於每個 clone 出去的
  專案都會收到同一封誤報，而且自己修不掉。安全性上等價（建置完就丟），
  BuildKit 的 cache key 也不含 secret 值，所以不影響快取。

- 文件補上 repo 設定裡的四個安全掃描開關（secret scanning、push protection、
  Dependabot security updates、code scanning）：模板該開哪些見
  [`docs/development.md`](docs/development.md#repo-設定裡的安全掃描)，
  **下游是 private 時哪些要付費**見
  [`docs/downstream.md`](docs/downstream.md#repo-設定裡的安全掃描模板的設定不會跟著複製過來)。
  這些設定不在版控裡，所以 clone 出來的專案一個都不會繼承。

- CI 重新分配各階段跑哪些 job。以「一次 draft push + Ready + merge」計，
  帳單從約 34 分鐘降到約 19 分鐘（實測值，不含 `publish`）：
  - **merge 到 `main` 只跑 `pushed-via-pr` 與 `publish`**，測試那六個 job 全部跳過。
    **這一條的前提是匯入 `.github/rulesets/main.json`**（strict：分支必須是最新才能
    merge，PR head 的 tree 才等於 merge 後的 tree）。**開案時要做的就是這件事** ——
    沒有匯入 ruleset 的話，把那六個 job 的 `if` 改回 `github.event_name != 'schedule'`。
  - `changelog`、`acceptance`、`test-edits` 三個 job 合併成 `pr-checks`（三個 step）。
    GitHub 逐 job 進位到整分鐘計費，三支各跑 4～6 秒卻各收一分鐘。
    **ruleset 的 required check 也跟著換成 `pr-checks`**，`make check-ci` 在守。
  - `security` 在 draft 期間不跑：它查的外部資料庫一天最多變一次，
    而 Ready 與每週一的 cron 已經是兩個落點。
  - tag build 完全不受影響，照跑全套 —— 那份 image 就是要上線的東西。
- dependabot 的三個基底映像 entry 從 monthly 改回 weekly。
  當初改 monthly 的理由是計費，而那個理由已經被上面那條與「repo 轉 public」拿掉了。
  下游是 private 而且分鐘數吃緊的話，改回 monthly 是一行的事，見
  [`docs/downstream.md`](docs/downstream.md#actions-分鐘數與-dependabot)。

- CI 依 PR 階段分配工作量，把每月的 Actions 分鐘數從約 1550 壓到約 870
  （免費私有 repo 的額度是 2000）。紅綠燈出現的時機變了：
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
- dependabot 的三個 base image entry（兩個 Dockerfile、一組 compose）
  從 weekly 改成 monthly；`uv` 與兩個 `npm` 維持 weekly。**代價**：OS 層的 CVE 修補最多
  延後一個月，而 `make audit` 掃不到那一層，期間不會有任何紅燈。理由與改回去的條件寫在
  [`.github/dependabot.yml`](.github/dependabot.yml) 的基底映像那一段。

## [0.0.1] - 2026-08-29

初始專案模板。功能概覽見 [`README.md`](README.md)，開案步驟見 [`TEMPLATE.md`](TEMPLATE.md)。
