# 開案後指南

這份文件是給**用這個模板開出來的新專案**看的：開案之後要做的一次性決定 ——
CI/CD 留哪些、安全掃描開哪些、Actions 分鐘數怎麼算。開案本身的步驟在
[`../TEMPLATE.md`](../TEMPLATE.md)（那份導入完成就該刪掉）。

> **這裡沒有「上游」。** 這個模板是 GitHub template repository，你拿到的是一份快照 ——
> 沒有共同歷史，也沒有 `template` remote 要維護。**所有檔案都是你的**，包含 `shared/`
> 與組裝層，改任何地方都不需要顧慮同步。代價是模板日後的修正不會自動流過來，
> 那個取捨寫在 [`../TEMPLATE.md`](../TEMPLATE.md)。

## 開案時先做這兩件

（`TEMPLATE.md` 的清單裡也有，這裡重述是因為漏掉不會有任何錯誤。）

- 清空 [`../CHANGELOG.md`](../CHANGELOG.md) 的條目，從你自己的第一版開始寫
  （模板的歷史留在模板 repo 上）。
- `apps/api/app/config.py` 的 `APP_VERSION` 是**你的產品版號**了，重新從你要的起點開始。
  `make check-version` 會比對它與 `CHANGELOG.md` 最上面那個版號標題
  （還沒發過版、一個版號標題都沒有時它會略過）。

## CI/CD

模板附的 `.github/workflows/` 是**可以直接用、也可以整個刪掉**的：

| 檔案／job | 下游要做什麼 |
|---|---|
| `ci.yml` 的 `api`／`web`／`deploy-config`／`security`／`api-types-up-to-date` | 直接用 |
| `ci.yml` 的 `pr-checks` | **三個 step 各自決定，job 本身留著。** 「CHANGELOG」那一步守的是模板的發布紀律，下游有自己的節奏，**可以刪掉那一步**；「驗收條件」與「改到既有測試」兩步**看你怎麼開發**（要求見 [`development.md`](development.md#規格與測試的三層)），它們的價值來自跟 AI agent 協作時「規格與測試需要一個機器守得住的落點」—— 純人力團隊的 review 讀得到那種 diff，那就可以刪。三步全刪的話整個 job 拿掉，ruleset 也要跟著拿掉 `pr-checks` 這個 context，不然 `make check-ci` 會紅 |
| `ci.yml` 的 `e2e` | 直接用。操作與範圍見 [`development.md`](development.md#e2e-的範圍)；移除範例模組時同步清掉對應測試，見 [`architecture.md`](architecture.md#移除-module) |
| `ci.yml` 的 `pushed-via-pr` | 直接用。它在「沒經過 PR 就進了 `main`」時紅燈，是分支保護的第二層 |
| `.githooks/pre-push` | 直接用，`make setup` 會掛上。第一層，擋直接 push 與 force push |
| `.github/rulesets/main.json` | **強烈建議匯入，而且它不只是分支保護。** repo 是 public 或付費方案時匯入一次（private + 免費方案設不了，403）。`ci.yml` 讓 merge 到 `main` 那一輪不重跑測試，**前提就是它的 strict 政策**（分支必須是最新才能 merge）—— 沒匯入的話那個推論不成立，要照 [`development.md`](development.md#4-測試) 說的把六個 job 的 `if` 改回去 |
| `ci.yml` 的 `publish`、`deploy.yml` | 要用 registry 部署才留，不用就照下面的清單刪掉 |

若自訂過 `.github/PULL_REQUEST_TEMPLATE.md`，同步時保留「驗收條件」與「改動到既有測試」
兩段的標題與填寫格式，使用時再依改動保留適用段落；規則見
[`development.md`](development.md#規格與測試的三層)。

分支保護的三個層次與各自擋得住什麼，見
[`development.md`](development.md#分支保護) —— 那一節是這個主題的 owner。

## repo 設定裡的安全掃描：模板的設定不會跟著複製過來

secret scanning、push protection、Dependabot security updates 與 code scanning（CodeQL）
**都是 GitHub 那一側的 repo 設定，版控裡沒有它們**，所以 clone 出來的專案一個都不會繼承 ——
要自己開一次。四個開關與建議的組合見
[`development.md`](development.md#repo-設定裡的安全掃描)，那一節是 owner。

**但那一節的建議是以 public repo 為前提的**，下游是 private 的話差別很大：

| | public | private |
|---|---|---|
| Secret scanning + push protection | 免費 | 要 GitHub Advanced Security（付費） |
| Code scanning（CodeQL） | 免費 | 同上 |
| Dependabot security updates | 免費 | 免費 |

也就是說 private 下游能白拿的只有最後一項（而它剛好也是最省事的一項，
見底下〈[Actions 分鐘數與 dependabot](#actions-分鐘數與-dependabot)〉的折衷）。
**不要因為模板開著就照抄** —— 沒有 GHAS 的 private repo 開 code scanning 的下場是
workflow 照跑、吃完分鐘數，然後在上傳結果那一步 403。

`make check-ci` 守著 ruleset 的 job 名單與 `ci.yml` 一致，所以**動 job 就要同時動 ruleset**
（沒有那個檔案就跳過，不會紅）。整套 GitHub Actions 都不用時把 `.github/` 刪掉即可，
`check-ci` 一樣會自己跳過。

要用 registry 部署的話，`production` environment、GitHub secrets／variables 與主機端的
`docker login` 是一次性設定，清單在
[`operations.md`](operations.md#registry-模式build-once-deploy-anywhere) ——
**不要在這裡再抄一份**，那一節是那個主題的 owner。

`publish` job 推的是 `ghcr.io/<你的 owner>/<你的 repo>/api` 與 `/web`，
沿用 `github.repository`，所以 fork／改名之後不必改設定。

## Actions 分鐘數與 dependabot

**這一節只給 private 專案。repo 是 public 的話 Actions 分鐘數無限，整節跳過** ——
而且 public 還順帶讓 [`main.json`](../.github/rulesets/main.json) 匯得進去（見上面那張表）
與四個安全掃描開關免費（見上面〈[repo 設定裡的安全掃描](#repo-設定裡的安全掃描模板的設定不會跟著複製過來)〉）。
模板預設走的就是 public 這條路，
開案步驟見 [`../TEMPLATE.md`](../TEMPLATE.md)。

還是 private 的話，先知道成本怎麼算：**免費方案的 2000 分鐘／月是「每個帳號」的，
不是每個 repo 的。** 所有 private repo 共用同一池 —— 包括模板自己。所以「從模板長出
三個下游專案」不是三份額度，是同一份被切成三份。

接著確認兩件已經做在模板裡的事還在，它們比刪 dependabot entry 有效得多：

- **merge 到 `main` 那一輪不重跑測試**（省約 12 分鐘／次），前提是匯入了 ruleset ——
  見上面那張表與 [`development.md`](development.md#4-測試)。
- **秒級的檢查合併成一個 `pr-checks`**。GitHub 是逐 job 進位到整分鐘計費的，
  所以新增 job 的下限成本是一分鐘，跟它跑多久無關。

做完這兩件之後，dependabot 的成本已經從「每個 PR 兩輪完整 CI」降到「一輪」。
那一輪仍然是它最主要的開銷，而且跟「這次有沒有東西可更新」無關，只跟開了幾個 PR 有關 ——
所以下面這張表仍然有用，只是沒有原本那麼急。

[`.github/dependabot.yml`](../.github/dependabot.yml) 會**原封不動跟著模板複製過來**，
所以新專案預設是照跑六組的。**六組都是你的東西**（沒有上游會幫你更新任何一組），
所以「刪掉」等於「那份 manifest 從此不再有人盯版本」——
`Dockerfile` 的基底映像尤其危險，它沒有 `make audit`、也沒有任何紅燈會提醒。

真的要省，先調頻率而不是刪除。三個基底映像的 entry 如果留著，可以把它們的 `schedule.interval` 從 `weekly` 改成
`monthly`（模板出廠是 weekly）。**代價**：基底映像沒有 `make audit` 也沒有任何紅燈在守，
OS 層的 CVE 最多會延後一個月修補，期間完全沒有症狀。理由寫在
[`.github/dependabot.yml`](../.github/dependabot.yml) 的基底映像那一段。

`uv`／`npm` 那三組如果還是太貴，有個折衷：把它們也刪掉，改在 repo 的
**Settings → Code security** 開 Dependabot security updates。那是獨立於這個檔案的開關，
只在真的有 advisory 命中你的 lockfile 時才開 PR —— 平常零成本，仍然守得住下游自己的相依。
**代價**：不再有例行的版本推進，只修有漏洞的，所以相依會慢慢舊到某天升不動
（那時的痛苦見 [`development.md`](development.md#相依升級紀律)）。

刪整組就是把那個 entry 從 `updates:` 拿掉，**沒有檢查器在守這個檔案** ——
`make check-ci` 只看 `ci.yml` 與 ruleset。

**不要為了省分鐘數改用 self-hosted runner。** 它確實不計費（GitHub 只對 hosted runner 計費），
但那條路只在 repo 是 private 時才安全 —— **public repo 掛 self-hosted runner 等於讓任何人
用一個 fork PR 在你的機器上執行任意程式碼**。而如果你的 repo 已經是 private 到需要省分鐘數，
比較划算的順序是先回頭問「這個 repo 可以 public 嗎」，那一步同時解決分鐘數、分支保護與
安全掃描三件事。真的要自架，至少用容器化或 ephemeral runner，不要裸機常駐。

## 移除 CD

### 先分清楚「不啟用」與「移除」

**不啟用**是主機那一側的事：`.env` 的 `IMAGE_REGISTRY` 留空就是 `make prod` 就地建置，
那是 `make init` 產生的預設值，零動作。

**但這管不到 GitHub 那一側。** `publish` job 的觸發條件是 push 到 `main`，跟你有沒有
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
```

**有兩步沒有檢查器在守**：`ci.yml` 裡 `publish` job 刪得乾不乾淨（YAML 少縮排一層不會有人
告訴你，要看 Actions 頁面確認那個 job 真的不見了），以及 `Makefile` 的 `TARGETS` 有沒有
拿掉 `deploy`（漏了不會報錯，只是 `make deploy` 會說找不到目標）。
