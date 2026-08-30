# CI/CD 與 GitHub 那一側

這份文件是**設定在 GitHub 那一側、版控裡看不到**的那些東西的 owner：CI 有哪些 job、
分支保護、repo 的安全掃描開關、Actions 分鐘數，以及要不要留下內建的 CD。

它們有一個共同點：**repo 裡沒有任何檔案能證明它們被設定過**，所以只能靠這份文件記得
它們存在。`make check-ci` 守得到「`ci.yml` 與 ruleset 的 job 名單一致」，
守不到「這份 ruleset 有沒有真的匯入 GitHub」。

本機的測試怎麼跑、覆蓋率門檻與 advisory 的處理紀律在
[`development.md`](development.md#4-測試)；生產部署的操作在
[`operations.md`](operations.md#生產部署)。

## CI 有哪些 job，各自守什麼

CI（[設定來源](../.github/workflows/ci.yml)）在 push 到 `main`、push `v*` tag、
PR to `main`、每週一的排程，以及手動觸發（`workflow_dispatch`）上執行。

**不是每個階段都跑全部**，因為每個階段需要的答案不同：

| 階段 | 跑什麼 | 帳單 |
| --- | --- | --- |
| 開 draft PR（空 commit） | 什麼都不跑 —— commit message 帶 `[skip ci]`，見〈[落點要在動手之前存在](development.md#落點要在動手之前存在)〉 | 0 |
| draft 期間的每次 push | `api`、`web`、`api-types-up-to-date`、`pr-checks`（驗收條件那一步跳過） | 約 6 分 |
| 按下 Ready for review | 全部 —— `deploy-config`、`e2e`、`security` 是第一次跑，其餘是重跑 | 約 12 分 |
| Ready 之後再 push | 全部 | 約 12 分 |
| merge 到 `main` | **只有 `pushed-via-pr` 與 `publish`** | 1 分加 `publish` |
| push `v*` tag | 全部，加上 `publish` | |
| 每週一排程 | 只有 `security` | 1 分 |
| 手動觸發（`workflow_dispatch`） | 六個測試 job，`pr-checks` 除外（見下） | 約 12 分 |

**merge 那一輪不重跑測試，前提是 ruleset 已經匯入。** 它的
`strict_required_status_checks_policy` 要求「分支必須是最新的才能 merge」，所以 PR head
的 tree 就等於 merge 之後的 tree —— 那一輪重跑的是同一棵樹，零新資訊，實測 12 分鐘。
**沒有匯入 ruleset 的話這個推論不成立**（`main` 可能在 PR 開著的時候前進），那時候要把
`ci.yml` 裡那六個 job 的 `if` 改回 `github.event_name != 'schedule'`。匯入與否 repo 裡
看不到、`make check-ci` 也守不到，見〈[分支保護](#分支保護)〉。
tag build 不受這條影響，照跑全套 —— 那份 image 就是要上線的東西。

**切 job 的成本不是零。** GitHub 是**逐 job 進位到整分鐘**計費的：一輪完整 PR 實測是
7 分鐘的工作、14 分鐘的帳單，差額全部是那些只跑幾秒的 job 各自被收滿一分鐘。所以
`changelog`、`acceptance`、`test-edits` 三支（各 4～6 秒）合併成一個 `pr-checks`，
三個 step 各自保留自己的逃生門。**要新增 job 之前先問「這盞燈值得一分鐘嗎」** ——
值得的理由通常是「需要獨立的紅綠燈」或「可以跟別的 job 平行」，不是「這件事跟那件事不一樣」。

**按下 Ready 時其餘 job 照樣重跑，即使 SHA 沒變。** 這看起來很浪費（同一份 tree
必得同一個答案），但試過不行：被跳過的 job **仍然會產生一筆 `skipped` 的 check run**，
而 GitHub 取同名 check 的最新那筆 —— draft 期間那筆 `success` 會被蓋掉，PR 頁面顯示
`api — skipping`，跟「這個 PR 從頭到尾沒跑過 api」長得一模一樣。完整論證與實測結果在
[`ci.yml`](../.github/workflows/ci.yml) 的 `api` job 註解上。

`deploy-config`、`e2e` 與 `security` 在 draft 期間跳過則沒有這個問題：它們接著就會在
`ready_for_review` 補跑，最新那筆是真的結果。**但那個補跑會被 push 撞掉** ——
所以有 `draft-gated-jobs` 在守（見下面的清單）。`pr-checks` 裡的驗收條件那一步是
**step 層**的跳過，跳過時整個 job 仍然是 `success`，連這個問題都不會碰到。

- **api**（**只在 PR 與 tag 上跑**）：ruff → mypy → pytest（會起一個 PostgreSQL 跑整合測試）
- **web**（同 `api`）：eslint → tsc → vitest → next build
- **deploy-config**（**只在非 draft 的 PR 與 tag 上跑**）：`make check` 只涵蓋原始碼，
  所以部署設定與文件壞掉時前面那些 job
  會全部照樣綠燈。這個 job 補的就是那一塊 —— 那排 `check-*`、兩份 compose 設定、
  兩個 production image、備份工具能不能在 image 裡跑，以及斷言 `api` 確實等 `migrate`
  成功結束。**逐步清單看 `ci.yml` 本身**，不抄在這裡：手抄的清單一定會落後於 `ci.yml`，
  理由見〈[寫文件與註解的慣例](development.md#5-寫文件與註解的慣例)〉第 4 條
- **pr-checks**（只在 PR 上跑）：三件 PR-only 的紀律檢查，三個 step：
  - **CHANGELOG**：動到 `apps/`／`scripts/`／`infra/` 卻沒更新 `CHANGELOG.md` 就失敗。
    漏寫沒有症狀 —— 程式碼照樣進去，只是「這個版本改了什麼」少一筆。
    純重構可在 PR 標題加 `[skip changelog]` 放行
  - **驗收條件**（**draft 期間跳過**）：`make check-acceptance` 確認每條驗收條件
    都指向存在的測試；純文件等無行為變更的改動可在 PR 標題加 `[skip acceptance]`，
    規則見〈[常用指令](development.md#2-常用指令)〉。draft 期間要看那盞紅綠燈
    就自己跑 `make check-acceptance`
  - **改到既有測試**：`make check-test-edits` 要求刪改既有測試時附上說明，
    規則見〈[改到既有測試要說明](development.md#改到既有測試要說明)〉
- **draft-gated-jobs**（只在非 draft 的 PR 上跑）：檢查上面那三個 draft 期間跳過的 job
  有沒有真的補跑過。**它守的是一個沒有症狀的壞法** —— `ready_for_review` 觸發的補跑會被
  接著的 push 撞掉（實測到兩種成因：兩個 run 被 concurrency 互砍，或第二個 run 壓根沒建立），
  而 **`skipped` 對 required status check 算通過**，PR 頁面是綠的。所以它不去修那個 race，
  改成檢查結果：PR 已經 ready 卻還有 skipped 就紅燈，並告訴你推個空 commit 重新觸發。
  判斷用的是**當下**的 draft 狀態（`gh pr view`），不是事件 payload —— payload 記的是
  事件發生當時的狀態，讀它會跟著一起被騙過去
- **e2e**（**只在非 draft 的 PR 與 tag 上跑**）：`make e2e` 對隔離的 stack
  驗證跨層接縫，範圍與操作見〈[e2e 的範圍](development.md#e2e-的範圍)〉
- **security**（**非 draft 的 PR、tag 與排程上跑**；draft 不跑，因為它查的外部資料庫
  一天最多變一次，而排程與 Ready 那兩個落點已經涵蓋）：`make audit`。
  排程存在的理由與掃描範圍見〈[安全 advisory](development.md#安全-advisory)〉
- **api-types-up-to-date**（同 `api`）：重新產生型別並比對 `git diff`，
  擋下「改了後端 schema 卻忘記跑 `make gen-types`」
- **pushed-via-pr**（只在 push 上跑）：push 到 `main` 卻查不到對應的 PR 就紅燈，
  是分支保護的第三層，見〈[分支保護](#分支保護)〉
- **publish**（只在 push 上跑，PR 不跑）：把兩個 image 推上 GHCR，並為它們產生
  build provenance attestation。
  **兩條路徑的保證不同**：tag build 上 `needs` 那六個真的在同一個 commit 上跑過、全綠才發布；
  push 到 `main` 時那六個都是 skipped，image 的證據來自「同一棵 tree 在 PR 上綠過」
  （靠 ruleset 的 strict 政策撐住）。`if` 因此帶 `always()`，少了它 `main` 上會永遠不再推
  image 而且顯示 skipped —— 理由寫在那個 job 的註解上。
  它**不需要任何 repository secret**（用內建的 `GITHUB_TOKEN` 推 GHCR）。
  設定見 [`operations.md`](operations.md#registry-模式build-once-deploy-anywhere)，
  attestation 的驗證方式見 [`operations.md`](operations.md#deploy-workflow-做了什麼)，
  不走 registry 那條路時的刪除清單見〈[移除 CD](#移除-cd)〉

`workflow_dispatch` 是為了「對現在的 `main` 重跑一次完整 CI」而存在的 —— re-run 一個舊 run
跑的是舊 SHA，答不了那個問題（merge 那一輪刻意不重跑測試）。六個測試 job 的 `if` 因此
一併放行手動觸發；`pr-checks` 刻意不放行，它讀 PR 標題與描述，手動觸發時沒有那些東西。

### 調整 pr-checks 的三個 step

**三個 step 各自可以拿掉，job 本身留著。** 它們守的都是紀律而不是正確性，
所以「值不值得」跟團隊怎麼開發有關：

- **CHANGELOG** 那一步守的是發布紀律。有自己的發布節奏、或根本不發版時可以刪。
- **驗收條件**與**改到既有測試**兩步的價值來自跟 AI agent 協作時
  「規格與測試需要一個機器守得住的落點」（要求見
  [`development.md`](development.md#規格與測試的三層)）。純人力團隊的 review
  讀得到那種 diff，那就可以刪。

**三步全刪的話整個 job 拿掉，ruleset 也要跟著拿掉 `pr-checks` 這個 context**，
不然 `make check-ci` 會紅。

留著的話，[`../.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md)
**可以自訂，但要保留「驗收條件」與「改動到既有測試」兩段的標題與填寫格式** ——
`check-acceptance` 與 `check-test-edits` 讀的就是那兩段，改了標題它們會安靜地
什麼都驗不到。使用時再依這次的改動保留適用段落。

**補完 PR 描述之後不要按 re-run，要推一個 commit。** 這兩步讀的 `PR_TITLE`／`PR_BODY`
在 CI 上來自 `github.event.pull_request.body`，而**re-run 重放的是原本那份事件 payload** ——
描述是事件發生當下的那一版，你剛剛補的段落不在裡面。症狀很像檢查器壞了：本機
`make check-test-edits` 綠的（它走 `gh pr view` 讀當下的描述），CI 重跑幾次都還是同一句
「PR 描述沒有說明」。`pull_request` 的觸發清單裡也沒有 `edited`，所以光改描述不會重跑。
推一個 commit 產生新的 `synchronize` 事件，payload 才會帶上新的描述。
（`draft-gated-jobs` 改讀 `gh pr view` 就是為了避開同一個坑，見上面那個 job。）


## 分支保護

「PR 送出前必須通過 `make check`」與整套 CI，**沒有任何東西讓它變成強制** ——
沒有啟用分支保護時，PR 上的 job 全紅也 merge 得進去。

**所以 ruleset 要匯入，而且它不是選配的** —— 見下面〈[匯入 ruleset](#匯入-ruleset)〉，
那一段還說明了為什麼 `ci.yml` 的正確性現在依賴它。**ruleset 對 public repo 免費，
對 private repo 要付費方案**（免費方案連 API 都回 403），所以 private 專案設不了，
那時候要照〈[CI 有哪些 job](#ci-有哪些-job各自守什麼)〉說的把六個 job 的 `if` 改回去。

ruleset 之外還有兩層，**兩層都不是伺服器端強制，這一點不要誤會**。
它們的價值在「ruleset 還沒匯入」與「ruleset 涵蓋不到的路徑」：

| 層 | 是什麼 | 擋得住嗎 |
|---|---|---|
| [`../.githooks/pre-push`](../.githooks/pre-push) | 擋直接 push 到 `main`、force push 與刪除 | 本機擋得住，但 `--no-verify` 繞得過，沒跑過 `make setup` 的機器上根本不會執行 |
| CI 的 `pushed-via-pr` job | push 到 `main` 卻查不到對應的 PR 就紅燈 | **擋不住** —— 走到那裡東西已經在 `main` 上了。它留下的是紀錄 |

`pre-push`（三層裡的第二層）由 `make setup` 透過
`git config core.hooksPath .githooks` 掛上。
`core.hooksPath` 是 per-clone 設定、不跟著 clone 走，所以每個人都要跑過一次 `make setup`。
已經指向別處（例如你自己裝的 husky）時 `setup` 不會覆蓋，會印一行提醒。

`pushed-via-pr` 有**一個豁免**：建立 `main` 的那一次 push 不跑（`!github.event.created`）。
那時候 repo 才剛開，不可能有 PR —— 少了這個豁免，第一筆 CI 紀錄就是紅的，
而一個被解釋成「正常的」紅燈，等於這個 job 不存在。它的洞（刪掉 `main` 再重推）
寫在 job 自己的註解裡。

三件事裡 **force push 是唯一嚴重的**：`main` 被改寫之後，每一個已經 clone 或 fork 的人
下一次拉都會撞上分岔的歷史，而那要每個人各自處理。另外兩件的代價是「繞過 `pr-checks`」，
可以補救。

### 匯入 ruleset

[`../.github/rulesets/main.json`](../.github/rulesets/main.json) 是現成的，匯入一次就把上面兩層
從「唯一的防線」變回它們原本的角色（第二、三層）：

```bash
gh api --method POST repos/{owner}/{repo}/rulesets --input .github/rulesets/main.json
```

**這一行只適用第一次。** `POST` 是「建立」，之後每次改過 `main.json` 都要改用 `PUT`
更新既有那一份，先查出它的 id：

```bash
id=$(gh api repos/{owner}/{repo}/rulesets --jq '.[]|select(.name=="main")|.id')
gh api --method PUT repos/{owner}/{repo}/rulesets/"${id}" --input .github/rulesets/main.json
```

**改過之後再 `POST` 一次的話，GitHub 會多出第二個同名的 `main` ruleset** ——
名稱不要求唯一，兩個都是 active、兩個都生效。症狀很惡劣：required checks 看起來是對的
（新的那份確實有你剛加的 job），但舊的那份還在，兩份規則疊加，之後想調鬆任何一條時
你改到其中一個、另一個繼續擋著，**而且沒有任何地方會提示你有兩份**。
數量確認：`gh api repos/{owner}/{repo}/rulesets --jq '.[].name'` 應該只有一個 `main`。

它要求 `main` 只能經 PR 進入、禁止 force push 與刪除，並把**所有會在 PR 上跑的 job**
列為必要檢查；完整名單以 ruleset 與 [`ci.yml`](../.github/workflows/ci.yml) 為準。
`publish` 與 `pushed-via-pr` 不在裡面 —— 它們只在 push 上跑，PR 上不存在，列進去會讓每個 PR
都卡在等一個永遠不會來的檢查。

`make check-ci` 守著這份 JSON 與 [`../.github/workflows/ci.yml`](../.github/workflows/ci.yml)
的 job 名單一致（檔案不存在就跳過）。**新增 job 卻沒加進 ruleset 是完全沒有症狀的** ——
job 照跑，只是不再擋 merge。**但 `check-ci` 守不到「這份 JSON 有沒有真的匯入 GitHub」** ——
那是 repo 設定，repo 裡沒有東西看得到，而且改了 JSON 要重新匯入才會生效。

**這一步不做的話，`ci.yml` 有一個沒有症狀的洞。** merge 到 `main` 那一輪不重跑測試，
前提就是 ruleset 的 `strict_required_status_checks_policy`（分支必須是最新才能 merge）——
少了它，`main` 可能在 PR 開著的時候前進，於是進 `main` 的那棵 tree 沒有人驗過，
而 CI 全綠。要嘛匯入 ruleset，要嘛照〈[CI 有哪些 job](#ci-有哪些-job各自守什麼)〉說的
把六個 job 的 `if` 改回去，不要兩個都不做。

`required_approving_review_count` 出廠是 `0`，因為這個 repo 要能被一個人開起來用。
**團隊超過一個人時記得調高。**

## repo 設定裡的安全掃描

這一節與上面的分支保護是同一類東西：**設定在 GitHub 那一側，版控裡看不到，
所以只能靠文件記得它們存在**。四個開關，都在 Settings 的安全那一頁
（頁名被改過幾次，早期叫 Code security and analysis）：

| 開關 | 掃什麼 | 建議 |
|---|---|---|
| Secret scanning | 已推上去的內容裡有沒有金鑰 | 開 |
| └ Push protection | **推的當下就擋**，金鑰進不了歷史 | 開，而且這才是重點 |
| Dependabot security updates | 有 advisory 命中 lockfile 時自動開 PR | 開 |
| Code scanning（CodeQL） | **你自己寫的程式碼**的漏洞模式 | 開，用 default setup |

**push protection 是這四個裡唯一防得住不可逆事故的。** 其餘三個都是事後通知，
而金鑰一旦進了 git 歷史就永遠在裡面 —— 後面的 commit 刪掉它沒有用，repo 是 public 的話
幾秒內就被爬走了。它是 Secret scanning 底下的子開關，所以要先開上面那個。

介面名稱會動，所以指令比路徑可靠：

```bash
gh api --method PATCH repos/{owner}/{repo} -f 'security_and_analysis[secret_scanning][status]=enabled' -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled'
```

**這四個對 public repo 全部免費，private repo 只有 Dependabot security updates 免費** ——
secret scanning 與 code scanning 都要 GitHub Advanced Security。private 專案不要照抄這張表：
沒有 GHAS 卻開 code scanning 的下場是 workflow 照跑、吃完分鐘數，然後在上傳結果那一步 403。

第五個開關在同一頁：**Private vulnerability reporting**。
[`../.github/SECURITY.md`](../.github/SECURITY.md) 要人走 Security 分頁的
「Report a vulnerability」回報，而**那個按鈕要開了這個開關才會出現** ——
沒開的話那份文件指向一個不存在的入口，而回報的人只會改去開公開 issue：

```bash
gh api --method PUT repos/{owner}/{repo}/private-vulnerability-reporting
```

**Code scanning 選 default setup，不要 advanced setup。** 後者會產生一份
`.github/workflows/codeql.yml` 進版控，看起來比較符合這個 repo 的紀律，但它是負債：
code scanning 對 private repo 要 GHAS，沒有的話那份 workflow 會照跑、吃完分鐘數，
然後在上傳結果那一步 403 失敗 —— 等於在版控裡放一個固定紅的 job。
default setup 不進版控，什麼都不會留下。
順帶一提，它的 CodeQL 版本由 GitHub 自己維護，不會變成 dependabot 要盯的第八組 manifest。

query suite 選 **Default** 而不是 Extended／`security-and-quality`：後兩者多出來的查詢信心較低，
第一次開就吃一堆 false positive，而那的下場是大家學會按 dismiss，等於這個掃描沒開。

**CodeQL 的紅綠燈不要加進 [`../.github/rulesets/main.json`](../.github/rulesets/main.json)。**
兩個理由：`make check-ci` 要求 ruleset 的必要檢查恰好等於 `ci.yml` 裡會在 PR 上跑的 job，
而 CodeQL 的 job 不在那個檔案裡（default setup 根本沒有檔案），加了會紅；
而且用一個會有 false positive 的掃描擋 merge，通常換來的是「大家學會按 dismiss」。
它的定位是提示，不是閘門。

## Actions 分鐘數與 dependabot

**repo 是 public 的話 Actions 分鐘數無限，整節跳過。** 底下只給 private 專案。

先知道成本怎麼算：**免費方案的 2000 分鐘／月是「每個帳號」的，不是每個 repo 的。**
所有 private repo 共用同一池，所以帳號底下有幾個專案就是那份額度被切成幾份。

接著確認兩件已經做在 `ci.yml` 裡的事還在，它們比刪 dependabot entry 有效得多：

- **merge 到 `main` 那一輪不重跑測試**（省約 12 分鐘／次），前提是匯入了 ruleset ——
  而 private + 免費方案匯不進去，見〈[分支保護](#分支保護)〉。
- **秒級的檢查合併成一個 `pr-checks`**。GitHub 逐 job 進位到整分鐘計費，
  所以新增 job 的下限成本是一分鐘，跟它跑多久無關。

做完這兩件之後，dependabot 的成本已經從「每個 PR 兩輪完整 CI」降到「一輪」。
那一輪仍然是它最主要的開銷，而且跟「這次有沒有東西可更新」無關，只跟開了幾個 PR 有關。

[`../.github/dependabot.yml`](../.github/dependabot.yml) 出廠盯七組 manifest
（`uv`、兩組 `npm`、兩個 `Dockerfile`、compose，加上 `github-actions`）。
**七組都是這個專案自己的東西**，所以「刪掉」等於「那份 manifest 從此不再有人盯版本」——
`Dockerfile` 的基底映像尤其危險，它沒有 `make audit`、也沒有任何紅燈會提醒。

真的要省，**先調頻率而不是刪除**：三個基底映像的 entry 可以把 `schedule.interval` 從
`weekly` 改成 `monthly`。**代價**：基底映像沒有 `make audit` 也沒有任何紅燈在守，
OS 層的 CVE 最多會延後一個月修補，期間完全沒有症狀。理由寫在
[`../.github/dependabot.yml`](../.github/dependabot.yml) 的基底映像那一段。

`uv`／`npm` 那三組如果還是太貴，有個折衷：把它們也刪掉，改在 repo 的
**Settings → Code security** 開 Dependabot security updates。那是獨立於這個檔案的開關，
只在真的有 advisory 命中 lockfile 時才開 PR —— 平常零成本，仍然守得住相依。
**代價**：不再有例行的版本推進，只修有漏洞的，所以相依會慢慢舊到某天升不動
（那時的痛苦見 [`development.md`](development.md#相依升級紀律)）。

刪整組就是把那個 entry 從 `updates:` 拿掉，**沒有檢查器在守這個檔案** ——
`make check-ci` 只看 `ci.yml` 與 ruleset。

**不要為了省分鐘數改用 self-hosted runner。** 它確實不計費（GitHub 只對 hosted runner 計費），
但那條路只在 repo 是 private 時才安全 —— **public repo 掛 self-hosted runner 等於讓任何人
用一個 fork PR 在你的機器上執行任意程式碼**。而如果 repo 已經 private 到需要省分鐘數，
比較划算的順序是先回頭問「這個 repo 可以 public 嗎」，那一步同時解決分鐘數、分支保護與
安全掃描三件事。真的要自架，至少用容器化或 ephemeral runner，不要裸機常駐。

## 部署主機的架構

**只在走 registry 模式（內建的 CD）時才需要讀這一節。** `make prod` 就地建置不受影響。

`publish` 出廠只建 `linux/amd64`，因為它沒有指定 `platforms`，出來的就是 runner 的原生架構。
**部署主機是 arm64 的話 image 拉得下來、跑不起來** —— 而同一台主機上 `make prod` 卻是好的
（就地建置用的是主機自己的架構），所以症狀不會指回 `publish`。

現在 arm64 的雲端主機（Graviton、Ampere）常常比同價位的 amd64 划算，所以這不是罕見情況。
**選主機的時候就決定**，不要等到第一次部署失敗：改法與兩種做法的取捨（QEMU 模擬
vs. `ubuntu-24.04-arm` 平行 job）見
[`operations.md`](operations.md#registry-模式build-once-deploy-anywhere) 那一節裡
「只建 linux/amd64」那一段 —— 那一節是這個主題的 owner。

## 移除 CD

### 先分清楚「不啟用」與「移除」

**不啟用**是主機那一側的事：`.env` 的 `IMAGE_REGISTRY` 留空就是 `make prod` 就地建置，
那是 `make init` 產生的預設值，零動作。

**但這管不到 GitHub 那一側。** `publish` job 的觸發條件是 push 到 `main`，跟有沒有
填 `IMAGE_REGISTRY` 無關 —— 它不需要任何額外設定就會成功，所以留著不會紅燈，
只會一直往 GHCR 推沒有人用的 image（外加每次 merge 的那幾分鐘 Actions 時間）。
不打算走 registry 的話照下面刪乾淨。

### 逐項清單

| 位置 | 動作 |
|---|---|
| `.github/workflows/deploy.yml` | 整份刪掉 |
| `.github/workflows/ci.yml` | 刪 `publish` job，連同它的 `permissions`、`env` 與抬頭那段註解 |
| `scripts/deploy.sh` | 刪掉，並把 `Makefile` 的 `TARGETS` 拿掉 `deploy` |
| `.env.example`、`scripts/init.sh`、`scripts/check-env.sh` | 三處一起拿掉 `IMAGE_REGISTRY`／`IMAGE_TAG`（`check-env.sh` 那一處是 `HOST_ONLY` 那一行） |
| [`operations.md`](operations.md) | 刪掉「registry 模式」整節，並把「生產部署」開頭的「兩條路」改成一條 |
| [`development.md`](development.md) | 常用指令表拿掉 `make deploy` |
| 這份文件 | 刪掉〈[部署主機的架構](#部署主機的架構)〉與這一節 |
| GitHub 設定 | `production` environment 與 `DEPLOY_*` 那組 secrets／variables 都不必建 |

**兩處刻意不動**，不要順手清掉：

- `infra/docker/docker-compose.yml` 的 `API_IMAGE`／`WEB_IMAGE`／`IMAGE_PULL_POLICY`
  都帶預設值，沒有 registry 時它們自己退回就地建置。拿掉反而要改 compose 的三個地方，
  換來的只是少三個用不到的變數。
- `.github/dependabot.yml` 的 `github-actions` 那組：`ci.yml` 剩下的 job 還在用 action，
  仍然需要有人盯著版本。

刪完跑這四支：

```bash
make check-env      # IMAGE_REGISTRY／IMAGE_TAG 三處是否清得一致
make check-docs     # 文件裡還指著 scripts/deploy.sh 的地方（operations.md 有好幾處）
make check-shell
make check-compose
make check-ci       # 內含 actionlint，會抓到刪壞的 YAML
```

**有兩步沒有檢查器在守。** 一是 `Makefile` 的 `TARGETS` 有沒有拿掉 `deploy`
（漏了不會報錯，只是 `make deploy` 會說找不到目標）。二是 `publish` job **刪得夠不夠、
有沒有刪過頭** —— `check-ci` 的 actionlint 擋得住「刪成無效的 YAML」，但擋不住
「順手把隔壁的 job 一起刪掉了」：那仍然是合法的 YAML，而 `check-ci` 只比對 ruleset 與
`ci.yml` 的 job 名單一致，兩邊一起少掉一個 job 它是對得上的。
刪完到 Actions 頁面確認剩下的 job 就是你要的那些。

## 整套都不用

`.github/` 可以整個刪掉，本機的 `make check` 與其餘 `check-*` 不受影響
（`make check-ci` 沒有 `ci.yml` 會自己跳過）。但要知道刪掉的是什麼：
ruleset 的來源檔（`.github/rulesets/main.json`）與分支保護的第三層
（`pushed-via-pr`）、`api-types-up-to-date` 那道
「改了 schema 忘記跑 `make gen-types`」的防線，以及 `deploy-config` 涵蓋的
那一整塊 `make check` 碰不到的東西。`.githooks/pre-push` 不在 `.github/` 底下，會留著。
