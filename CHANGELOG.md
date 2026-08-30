# 變更紀錄

這個 repo 的實質改動記在這裡，版本對應 `apps/api/app/config.py` 的 `APP_VERSION`。

**用這個模板開出新專案時**：把底下的條目清空，從你自己的第一版重新開始寫
（`APP_VERSION` 也一起重設）。模板的歷史留在模板 repo 上，不需要跟著複製到每個專案。

條目怎麼寫與 `## [Unreleased]` 的用法見
[`docs/development.md`](docs/development.md#changelog-條目)，
發版步驟見 [`docs/operations.md`](docs/operations.md#發版與回滾)。

## [Unreleased]

### 變更

- **整份讀過 `docs/` 六份文件，修掉 15 處殘留與不一致。** 全部是檢查器守不到的類別 ——
  `check-docs` 驗的是路徑、錨點與識別字存不存在，驗不到「這句話描述的東西已經不是這樣了」：
  - **`operations.md` 的 Session 撤銷表殘留 MongoDB 用語**：`auth_version` 寫成存在
    「`users` **文件**」、重設密碼時「自動 **`$inc`**」。這是全 repo 唯一一處 MongoDB 詞彙，
    而實作是 PostgreSQL 上的 `auth_version = cls.auth_version + 1`（`modules/users/model.py`）。
  - **舊「可同步上游」模型的最後三處**，全是同一句「**模板更新時**新增的權限／欄位要能補到
    既有環境」：`extending.md` 的 Seed 一節、`shared/db/table.py` 的 `seed_match_key`
    docstring、`tests/shared/test_seed.py` 的測試 docstring。快照模式下沒有「模板更新」
    這件事，而那條分岔本身仍然需要 —— 理由改成「日後新增的權限要能補到已經跑起來的環境」。
  - **`development.md` 的〈什麼時候跑 e2e〉說 merge 到 `main` 會跑，但 `ci.yml` 明說不跑。**
    這條會讓人以為 merge 之後還有一道 e2e 網。改成不跑，並寫明前提是 ruleset。
  - **`ci.yml` 的 e2e job 註解仍寫著「理由同 deploy-config job：計費」**，而 deploy-config
    那段早就改成回饋速度、並註明計費那個理由已經不成立。指過去卻複述了被撤銷的理由。
  - **`architecture.md` 剝除 `push` 的清單漏了一個位置**：`ci.yml` 有**兩份**驗證用假 `.env`
    （`deploy-config` 與 `e2e`），原本只列了前者的 `VAPID_*` 三行。
  - 四處計數對不上：`design-system.md`「四條保證」對三列表格、`development.md`
    〈相依升級紀律〉「照這三條」對四條、`operations.md`「七件事」對八個項目、
    以及 `gh` 設定腳本從 `# 6` 直接跳到 `# 8`。
  - 三處內部指路壞掉：`development.md` 兩處指向〈測試與覆蓋率〉（實際章節叫〈覆蓋率門檻〉）、
    一處「上面那 90 秒」而文件裡從沒出現過 90 秒（它在 `playwright.config.ts`）、
    `design-system.md` 一處「見下面」指的其實在上面。
  - `extending.md` 說 `shared/i18n/` 是「約 100 行」，實際 266 行 —— 那句話要撐的論證是
    「小到不值得引入框架」，數字錯了論證就變弱。

- **修掉 `TEMPLATE.md` 的四處內部不一致。** 都是在它自己被改了好幾輪之後留下的，
  `check-docs` 守的是路徑與錨點，這四種一個都守不到：
  - §5a 標題還寫「三件事」，內文已經是四件（`Private vulnerability reporting`
    是後來加的）。
  - 同一節那句「那行 `POST` 是首次匯入用的」離它指的指令 18 行遠，中間還夾了另一個
    `gh api` 區塊 —— 照字面讀會以為指的是後面那行 `PUT`。說明搬回指令正下方，
    四件事改成連續的粗體編號。
  - 附錄那句「唯一的替代路徑（clone 之後 `rm -rf .git`）會讓開案的人拿到一份帶著
    完整歷史的 repo」**自相矛盾** —— 真的做了 `rm -rf .git` 就沒有歷史了。
    會出事的是**漏掉那一步**，改寫成那樣。
  - §1 的「走完這份清單之後再刪掉 `TEMPLATE.md`」插在開案指令與「打開瀏覽器」中間，
    把 §1 的流程打斷；§6 本來就是講這件事的，那句拿掉。
  - §5b 對 CI 的概述補上 e2e 與相依漏洞掃描。

- **文件重整：新增 [`docs/ci-cd.md`](docs/ci-cd.md)，移除 `docs/downstream.md`。**
  原本的 `downstream.md` 把兩種壽命不同的東西寫在一起：**開案期**的模板自我說明
  （「模板附的」「這裡沒有上游」）與**永久有用**的 CI/CD 知識，而後者被寫成前者的語氣，
  導致開案之後那份文件整份都不能原樣留著。現在以壽命切開：
  - `docs/ci-cd.md` 是 GitHub 那一側的 owner —— CI 有哪些 job 各自守什麼、分支保護與
    ruleset、repo 的四個安全掃描開關、Actions 分鐘數與 dependabot、部署主機的架構、
    移除 CD 的逐項清單。用專案語氣寫，不提「模板」，開案之後原樣留著。
  - 開案期的內容併進 [`TEMPLATE.md`](TEMPLATE.md)（清空 CHANGELOG 與重設 `APP_VERSION`、
    public vs. private 的差別表），**所以 `docs/` 現在 100% 是永久內容** ——
    分家只要 `git rm TEMPLATE.md`，不必再判斷 `docs/` 裡哪幾份該刪。
  - 連帶把 `development.md` 的〈分支保護〉〈匯入 ruleset〉〈repo 設定裡的安全掃描〉
    與 §4 的 CI job 清單搬進 `ci-cd.md`。`development.md` 收回它本來的範圍
    （本機開發紀律），兩邊改成單向連結，不再互指。

- **清掉四處已經不成立的敘述**，檢查器全部抓不到（`check-docs` 守的是路徑與錨點存在，
  守不到「這段文字描述的東西已經沒了」）：`operations.md` 說「上游打的 tag 會出現在每個
  下游的 `git tag -l` 裡」（快照模式下沒有上游）、`operations.md` 兩處
  `NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` 的「曾經是…現在是…」（演進史只該留在這裡，
  見 [`docs/development.md`](docs/development.md#5-寫文件與註解的慣例) 第 3 條）、
  `development.md` 疑難排解表的「同步上游後多了新變數」、`check-version.sh` 把存在理由
  寫成「下游判斷落後多少、同步要做什麼」。另外 `development.md` 的〈安全 advisory〉
  原本說「祕密不會進版控的唯一防線是 `.gitignore`」，那在 push protection 進來之後
  就不對了，改寫成兩層各自守什麼。

- **更新 ruleset 的指令從 `POST` 改成 `PUT`（三處）。** `POST` 是「建立」不是「更新」——
  第一次匯入時它是對的，但改過 `main.json` 之後照著做，GitHub 會多出**第二個同名的
  `main` ruleset**（名稱不要求唯一），兩個都是 active、兩份規則疊加。症狀很惡劣：
  required checks 看起來是對的（新的那份確實有你剛加的 job），但舊的那份還在，
  之後想調鬆任何一條時會改到其中一個、另一個繼續擋著，**而且沒有任何地方會提示你有兩份**。
  三處裡 `scripts/check-ci.sh` 那行最關鍵 —— 它印出來的時機必定是「ruleset 剛被改過」，
  也就是唯一需要 `PUT` 的情境。`TEMPLATE.md` 的開案情境確實是首次匯入，`POST` 維持不動，
  只補一句指路。

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

- **改用 GitHub template repository 模式，不再提供可同步的上游。** 新專案用
  "Use this template" 開出來，拿到的是一份快照：沒有共同歷史、沒有 `template` remote、
  之後也不會有同步。**所以新專案可以改任何地方**，包含 `shared/` 與組裝層。
  取捨與理由寫在 [`TEMPLATE.md`](TEMPLATE.md) 的第 0 節（一句話：可同步的上游要成立，
  前提是每個專案都遵守「不要改 `shared/` 與組裝層」，而多個平行開發的專案幾乎必然破壞它；
  破壞之後就是付了成本卻拿不到好處）。連帶：
  - 移除 `make sync`／`scripts/sync.sh` 與 `make remote`／`scripts/remote.sh`。
    快照模式下正常開案（"Use this template" 之後 `git clone`）`origin` 早就綁好了，
    `remote` 一次都不會被呼叫；剩下的退路（下載 ZIP、`rm -rf .git`）用兩行標準 git 指令
    就夠，而它最複雜的那段（判斷共同祖先、警告 unrelated histories）本來就是為舊模型寫的。
  - **變更紀錄維持單一份 `CHANGELOG.md`。** 開發過程中一度拆成
    `CHANGELOG.template.md` 加一份種子檔，那是為了讓「模板與下游持續寫進同一條血脈」
    不會永遠衝突而設計的；快照模式下同一時間只有一個 owner，拆開就只剩成本。
    連帶 `make check-version` 不再需要判斷「這個 repo 是模板還是新專案」，
    CI 的 CHANGELOG 守衛也從兩個方向縮回一個（只擋漏寫）。
  - 移除 CHANGELOG 條目的同步影響標記與 `make check-version` 對它的檢查。
  - `AGENTS.md` 移除「有 `template` remote 就不要改 `shared/`」那條規則。
  - `TEMPLATE.md` 第 6 步從「順手 grep 一下」改成逐檔清單。**照原本的寫法走完清單會讓
    下游第一個 PR 紅燈** —— `git rm TEMPLATE.md` 之後有十幾條 markdown 連結斷掉，散在
    多個檔案，而 `check-docs` 在 CI 的 `deploy-config` job 裡。
  - `TEMPLATE.md` 的附錄補上「repo 的 `Template repository` 開關要打勾」。整個開案模式
    建立在它上面，而它跟 ruleset、secret scanning 一樣是 GitHub 那一側的設定 ——
    版控裡看不到，也沒有任何檢查器守得到。

- `make init` 問資料庫帳號時的預設值從 `admin` 改成 `app`，與 `.env.example` 和
  `docs/development.md` 的表格一致。`check-env` 比對的是變數名不是預設值，所以這三處
  飄了沒有任何症狀。

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

- **模板的預設立場改成「repo 是 public」，並補上 repo 設定裡的安全掃描開關。**
  免費方案上 public 與 private 拿到的東西差很多（Actions 分鐘數、ruleset、secret scanning、
  CodeQL、environment 的 required reviewers 五項），原本散在各處的「這是付費功能所以不預設」
  全部重寫。四個開關（secret scanning、push protection、Dependabot security updates、
  code scanning）**都是 GitHub 那一側的設定，版控裡沒有它們**，所以 clone 出來的專案
  一個都不會繼承 —— 建議的組合與 private 的差別見
  [`docs/ci-cd.md`](docs/ci-cd.md#repo-設定裡的安全掃描)。
  - **`ruleset` 從「選配」變成「開案必做」**：`ci.yml` 讓 merge 到 `main` 那一輪不重跑測試，
    前提就是它的 strict 政策 —— 沒匯入的話那個洞**沒有任何症狀**。
  - `deploy-config` 與 `e2e` 在 draft 期間跳過的理由從「計費」改成「回饋速度」。
    行為沒變，但理由變了：public 之後分鐘數無限，留著舊理由會讓人以為可以全開回去。
  - 新增警告：**public repo 不能掛 self-hosted runner**（fork PR 可以在你的機器上
    執行任意程式碼）。
  - public repo 的部署主機可以匿名 `git fetch`，deploy key 那段只有 private 需要。
  - **Code scanning 選 default setup 而不是 advanced setup**：後者會產生一份
    `codeql.yml` 進版控被每個下游繼承，而 code scanning 對 private repo 要付費 ——
    等於送給每個 private 下游一個固定紅的 job。

- `ci.yml` 裡三個寫死的假金鑰改成每次執行時現產（`openssl rand -base64 32`）。
  值本來就是假的（解開來是 `ci-only-not-a-real-key-32bytes!!`），但泛型的 secret 掃描器
  只看熵，照樣判成外洩並寄信 —— 而那串字會被**每一個下游繼承**，等於每個 clone 出去的
  專案都會收到同一封誤報，而且自己修不掉。安全性上等價（建置完就丟），
  BuildKit 的 cache key 也不含 secret 值，所以不影響快取。

- **CI 依 PR 階段分配工作量。** 以「一次 draft push + Ready + merge」計，
  帳單從約 34 分鐘降到約 19 分鐘（實測值，不含 `publish`）：
  - **merge 到 `main` 只跑 `pushed-via-pr` 與 `publish`**，測試那六個 job 全部跳過。
    **這一條的前提是匯入 `.github/rulesets/main.json`**（strict：分支必須是最新才能
    merge，PR head 的 tree 才等於 merge 後的 tree）。沒有匯入 ruleset 的話，
    把那六個 job 的 `if` 改回 `github.event_name != 'schedule'`。
  - `deploy-config`、`e2e` 與 `security` 在 draft 期間不跑，按下 Ready for review 時補跑。
    draft 期間要看這幾盞燈就自己跑 `make check-compose`／`make e2e`／`make audit`。
    `security` 查的外部資料庫一天最多變一次，而 Ready 與每週一的 cron 已經是兩個落點。
  - **按下 Ready 時其餘 job 照樣重跑。** 試過不重跑，會讓 PR 頁面說謊 ——
    被跳過的 job 仍然會產生一筆 `skipped` 的 check run 蓋掉 draft 期間那筆 `success`，
    而 `skipped` 對必要檢查算通過。實測結果寫在 `ci.yml` 的 `api` job 註解上。
  - `changelog`、`acceptance`、`test-edits` 三個 job 合併成 `pr-checks`（三個 step）。
    GitHub 逐 job 進位到整分鐘計費，三支各跑 4～6 秒卻各收一分鐘。
    **ruleset 的 required check 也跟著換成 `pr-checks`**，`make check-ci` 在守。
  - 每週一的排程只跑 `security` —— 那本來就是那條 cron 唯一的存在理由。
  - 開 draft PR 的空 commit 建議帶 `[skip ci]`，見
    [`docs/development.md`](docs/development.md#落點要在動手之前存在)。
  - tag build 完全不受影響，照跑全套 —— 那份 image 就是要上線的東西。

## [0.0.1] - 2026-08-29

初始專案模板。功能概覽見 [`README.md`](README.md)，開案步驟見 [`TEMPLATE.md`](TEMPLATE.md)。
