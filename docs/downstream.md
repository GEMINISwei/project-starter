# 下游專案指南

這份文件是給**從模板 clone 出來的專案**看的：哪些目錄不該在下游改動，以及日後怎麼把
模板的修正拉回來。開一個新專案的步驟在模板的 `TEMPLATE.md`（那是一次性的，
你的專案裡應該已經刪掉了），不在這裡。

> **你在改的是下游專案，還是模板本身？**
> 這份文件是給前者的。判斷方法：`git remote -v` 有沒有一個叫 `template` 的遠端。
> 若你在改模板本身，看 [`development.md`](development.md)。
> **這份文件要留在你的 repo 裡** —— 每次同步都會用到。

## 同步紀律：不要在下游改 `shared/` 與組裝層

這是讓「拉更新」不會痛的唯一條件：

| 目錄／檔案 | 下游可以改嗎 |
|---|---|
| `apps/*/modules/` | **可以**，這是你的功能所在 |
| `apps/*/shared/` | **不要改**，要改請回上游改再同步 |
| 後端 `app/`、前端 `config/` | 只加自己模組的**清單項目**，不改機制 |
| `apps/web/app/` | 只加自己模組的薄 route adapter（wrapper 形式，見 [`architecture.md`](architecture.md)） |
| `apps/web/app/tokens/vendor/` | **完全是你的** —— 外部 DS 的原生產出，一套一個目錄，更新時整批覆蓋（每一份都要在 `app/layout.tsx` 與 `app/global-error.tsx` 各接一行 import，`check:tokens` 在守） |
| `apps/web/app/tokens/primitives.css` | **可以加自己的調色線**，指向 vendor；不要整份換掉（見下方） |
| `apps/web/app/tokens/semantic.css`、`app/themes/*.css` | **可以改對應，不可以改 token 的名字**（見下方） |
| `apps/web/config/theme.ts` | 預期你會改 `DEFAULT_THEME`；自訂主題就加進 `ThemeName` |
| `CHANGELOG.md` | **完全是你的** —— 模板不再碰這一份，所以它永遠不會衝突 |
| `CHANGELOG.template.md` | **不要改**，那是模板的紀錄，同步時整份跟著上游走 |
| `apps/api/app/config.py` 的 `APP_VERSION` | **改成你自己的產品版號**；同步時衝突留自己的（見下方） |
| `AGENTS.md` | **可以**加自己專案的規則，但預期會在同步時衝突（見下一節） |
| `README.md` | **要改寫成你自己專案的**，但先處理授權（見下方） |
| `TEMPLATE.md` | 開案指南，**導入完成後就該刪掉**；還在的話代表流程沒走完 |

樣式那幾列的規則只有一條：**語意層 token 的「名字」是模板的契約，「值」是你的。**
`shared/ui` 的 CSS 只認語意層的那組名字（`--color-surface-card`、`--space-4`…），
所以你可以把 `themes/*.css` 的對應全部重指到自己的色票、可以再加一份自己的主題，
但那些名字要留著 —— 改名等於把 UI kit 的樣式拔掉一半。

導入外部 DS 是**多一份主題**，不是覆蓋 `primitives.css`（內建的 `default` 留著，隨時切得
回去）。步驟見 [`design-system.md`](design-system.md) 的「導入外部 Design System」。

這條和上面那些不同，**它有檢查器在守**。把 `--color-surface-card` 改名之後跑
`npm run check:tokens`，每一個還在用舊名字的呼叫點都會逐行報「引用了沒有宣告過的
token」—— `shared/ui`、`config/shell` 與各模組的 CSS 都在其中。只改了其中一份主題檔
的話訊息會不一樣（變成那份主題「少宣告」某個 token），但一樣是紅燈。

token 分層的完整規則見 [`design-system.md`](design-system.md)。

`AGENTS.md` 是給 AI agent 的指引**本體**，任何工具都讀得到，請留著。根目錄的 `CLAUDE.md`
只是把它接進來的**轉接檔**（Claude Code 的慣例檔名）—— 這類轉接檔按你團隊實際使用的工具
增刪即可，刪掉不算破壞上面的同步紀律。

`AGENTS.md` 與 `TEMPLATE.md` 的生命週期是**相反**的，不要弄混：`TEMPLATE.md` 只在開案
那幾天有用，導入完成就刪；`AGENTS.md` 寫的規則要到你開始長功能才真正開始生效，
而且它們由 repo 裡持續存在的檢查器守著（`npm run check:architecture`、
`tests/test_architecture.py`、`make check-docs` 等），不會因為開案結束而失效。

**下游專案的授權要你自己決定並寫上** —— 理由與步驟在 [`../TEMPLATE.md`](../TEMPLATE.md)
的「改寫 README 與授權」（那是開案時就該做完的事；這裡只提醒，因為改寫 README 的時機
往往拖到開案之後）。

這條紀律不是憑空要求，而是既有架構撐得起來的：boundary checker 保證 `modules/`
不會被 `shared/` 反向依賴（`shared` 引用 `modules` 會直接檢查失敗），
所以 `shared/` 在拓撲上是一層可以獨立替換的東西。**破壞這個前提的代價是每次同步都要手動合併。**

真的需要改 `shared/` 時的正確做法：回模板改 → 模板升版 → 下游同步。
急件可以先在下游改，但要立刻回上游補同一份修正，否則下次同步一定衝突。

## 拉模板的更新

```bash
make sync
```

它會抓上游、**把落後的條目按同步影響分成「要動手」與「其餘」兩堆印出來**、顯示
`apps/`／`scripts/`／`infra/` 的改動範圍，確認之後才合併，合併完再提醒你跑
`make gen-types` 與 `make check`。分堆靠的是模板每一筆條目開頭的
`[同步:無]`／`[同步:要動手]`／`[同步:破壞性]` 標記（意思見
[`../CHANGELOG.template.md`](../CHANGELOG.template.md) 的檔頭，模板那邊有檢查器在擋漏標記）。

不想用它的話，等價的是這兩行 —— 差別只在你要自己讀完整份條目：

```bash
git fetch template
git merge template/main
```

**前置條件有兩個。** 一是有一個叫 `template` 的 remote —— 從 clone 開案的話是
`git remote rename origin template`，其餘情況用 `make remote`（名稱填 `template`、
網址填模板位置）。二是你的歷史與模板**有共同祖先**，也就是開案時保留了 clone 下來的
歷史；`make remote` 綁定時會檢查並在對不上時當場告訴你。兩者少一個，這一節都不成立。

**預期會衝突的地方分三類，解法不一樣，不要混著解。**

一是**清單**，因為下游會在同一份清單裡加自己的模組：

- `apps/web/config/routes.ts` 的 `ENABLED_MODULES`
- `apps/api/app/registry.py` 的 `ENABLED_MODULES`
- `apps/api/app/permissions.py` 的 `Permission` enum
- `apps/web/config/shell/nav-icons.ts`（偶爾）

清單的解法固定是**兩邊的項目都保留**（上游新增的 + 你自己的），不要二選一。

二是 **token 檔**（`apps/web/app/tokens/**`、`apps/web/app/themes/**`），
因為你會把它們重指到自己的色票。這裡**值以你的為準**，直接留下你自己那一份 ——
（接了外部 DS 的話，vendor 那幾檔根本不該出現衝突：它們是上游 DS 的產出，
整批覆蓋而不是手解，要合的只有對照表與主題檔。）
但如果上游這次**新增**了語意 token，光留自己的會少掉那個名字，而 `shared/ui`
已經在用它了。

所以 token 檔衝突解完之後一定要跑一次：

```bash
cd apps/web && npm run check:tokens
```

它會逐行列出「引用了沒有宣告過的 token」，那就是你要補的對應。反過來，
`make gen-types` 對這類衝突沒有幫助 —— 它管的是 API 契約，不是樣式。

三是 **`APP_VERSION`**（`apps/api/app/config.py` 那一行）：兩邊都在升自己的版號，
所以每次上游發版都會撞在同一行。**留自己的** —— 那個常數在你的專案裡記的是你的產品版本，
模板的版本改成從 [`../CHANGELOG.template.md`](../CHANGELOG.template.md) 最上面那個版號標題讀。
`make check-version` 會自己判斷這裡是模板還是下游（判準是 `TEMPLATE.md` 還在不在），
下游模式比對的是你自己的 [`../CHANGELOG.md`](../CHANGELOG.md)。

**兩份 CHANGELOG 都不會衝突**，那正是它們分家的理由：`CHANGELOG.md` 只有你在寫，
`CHANGELOG.template.md` 只有上游在寫。哪天真的衝突了，代表有一邊寫錯地方了。

如果你在 `AGENTS.md` 加過自己專案的規則，那份也會衝突，解法一樣是兩邊都保留 ——
上游改的是模板本身的規則，跟你加的專案規則不會是同一件事。

合併後必跑：

```bash
make gen-types   # 後端 schema 有變動時，前端型別要跟著重產
make check       # 已含 check:tokens
```

如果衝突出現在 `shared/` 底下，代表上一節的紀律被破壞了 —— 先把下游對 `shared/` 的修改
整理成一份補丁送回上游，再重新同步，不要在合併時硬解。

## 版本與變更紀錄

**兩份紀錄，兩個 owner，不要混用：**

| 檔案 | 誰在寫 | 記什麼 |
|---|---|---|
| [`CHANGELOG.md`](../CHANGELOG.md) | 你 | 你的專案的功能變更，版號對應你自己的 `APP_VERSION` |
| [`CHANGELOG.template.md`](../CHANGELOG.template.md) | 上游 | 模板的改動，版號是模板版；同步時整份跟著上游走 |

分家之前這是同一份檔案，於是同一個區塊有兩個 owner ——
結果是每次同步都衝突，而「我落後多少」那份 diff 裡混著自己寫的條目，讀不出來。

開發階段版號一律是 `0.x.x`，只有到「實際可上線」的第一個版本才升到 `1.0.0`；
下游專案自己接手後續開發時，也適用同一條規則。

### 判斷自己落後多少

```bash
make sync
```

不合併也可以只看清單 —— 在確認提示按 `N` 就好。想手動看的話：

```bash
git fetch template
git diff HEAD template/main -- CHANGELOG.template.md
```

那份檔案**只有上游在寫**，所以這個 diff 是單向的：新增行就是你還沒有的條目。
每一筆開頭的標記直接告訴你要不要動手，`make sync` 印出來的兩堆就是照它分的。

上游 CI 的 `pr-checks` 會擋掉「動了 `apps/`／`scripts/`／`infra/` 卻沒留條目」的 PR，
所以這份清單相當可信。**但它有一個放行方式**（PR 標題帶 `[skip changelog]`，
給純重構與相依升級用）。要百分之百確認的話請直接看程式碼：

```bash
git diff HEAD template/main --stat -- apps/ scripts/ infra/
```

（`make sync` 也會印這一段。）

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

`make check-ci` 守著 ruleset 的 job 名單與 `ci.yml` 一致，所以**動 job 就要同時動 ruleset**
（沒有那個檔案就跳過，不會紅）。整套 GitHub Actions 都不用時把 `.github/` 刪掉即可，
`check-ci` 一樣會自己跳過。

要用 registry 部署的話，`production` environment、GitHub secrets／variables 與主機端的
`docker login` 是一次性設定，清單在
[`operations.md`](operations.md#registry-模式build-once-deploy-anywhere) ——
**不要在這裡再抄一份**，那一節是那個主題的 owner。

`publish` job 推的是 `ghcr.io/<你的 owner>/<你的 repo>/api` 與 `/web`，
沿用 `github.repository`，所以 fork／改名之後不必改設定。

### Actions 分鐘數與 dependabot

**免費方案的 2000 分鐘／月是「每個帳號」的，不是每個 repo 的。** 所有 private repo
共用同一池 —— 包括模板自己。所以「從模板長出三個下游專案」不是三份額度，
是同一份被切成三份。

先看有沒有更大的槓桿：**repo 如果可以 public，Actions 分鐘數無限**，這一節就不用看了
（順帶連 [`main.json`](../.github/rulesets/main.json) 也才匯得進去，見上面那張表）。

private 的話，先確認兩件已經做在模板裡的事還在，它們比刪 dependabot entry 有效得多：

- **merge 到 `main` 那一輪不重跑測試**（省約 12 分鐘／次），前提是匯入了 ruleset ——
  見上面那張表與 [`development.md`](development.md#4-測試)。
- **秒級的檢查合併成一個 `pr-checks`**。GitHub 是逐 job 進位到整分鐘計費的，
  所以新增 job 的下限成本是一分鐘，跟它跑多久無關。

做完這兩件之後，dependabot 的成本已經從「每個 PR 兩輪完整 CI」降到「一輪」。
那一輪仍然是它最主要的開銷，而且跟「這次有沒有東西可更新」無關，只跟開了幾個 PR 有關 ——
所以下面這張表仍然有用，只是沒有原本那麼急。

[`.github/dependabot.yml`](../.github/dependabot.yml) 會**原封不動跟著模板複製過來**，
所以下游預設是照跑六組的。要省的話按「這份 manifest 是誰擁有的」切：

| 生態系 | 下游怎麼處理 | 為什麼 |
|---|---|---|
| `docker` ×2、`docker-compose`、`github-actions` | **刪掉** | `Dockerfile`、compose 與 `.github/` 都是模板擁有的，升版會隨著[拉模板的更新](#拉模板的更新)一起帶過來 —— 而且是一個 PR 帶全部，不是四組各開各的 |
| `uv`、`npm` ×2 | **不能全刪** | 下游會裝自己的相依，而模板對那些一無所知。只靠同步的話它們永遠不會被更新，那正是 `make audit` 掃得到、模板卻補不了的一層 |

三個基底映像的 entry 如果留著，可以把它們的 `schedule.interval` 從 `weekly` 改成
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

### 「不啟用」與「移除」是兩件事

**不啟用**是主機那一側的事：`.env` 的 `IMAGE_REGISTRY` 留空就是 `make prod` 就地建置，
那是 `make init` 產生的預設值，零動作。

**但這管不到 GitHub 那一側。** `publish` job 的觸發條件是 push 到 `main`，跟你有沒有
填 `IMAGE_REGISTRY` 無關；它第一步就檢查 repository secret
`NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` 在不在，沒設就紅燈。所以留著 CD 卻不用它並不是一個
穩定狀態，兩條路選一條：設好那支 secret（即使暫時不部署），或照下面刪乾淨。

### 移除 CD

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
