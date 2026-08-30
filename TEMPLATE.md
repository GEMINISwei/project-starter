# 開案指南（**導入完成後刪掉這一份**）

這份檔案只在「把模板變成你的專案」這段期間有用。走完下面的清單就
`git rm TEMPLATE.md`——留著它只會讓後續開發的人以為自己還在模板裡。

長期有效的規則不在這裡：開發規則見 [`AGENTS.md`](AGENTS.md)，
開案之後的一次性決定見 [`docs/downstream.md`](docs/downstream.md)。

## 0. 這個模板是快照，不是上游

**用 GitHub 的 "Use this template" 開新 repo**（或自己 clone 之後 `rm -rf .git` 重開歷史）。
你拿到的是一份**複製品**：沒有共同歷史、沒有 `template` remote、之後也不會有同步。

**所以這個 repo 裡的每一個檔案都是你的**，包含 `shared/` 與組裝層（後端 `app/`、
前端 `config/`）—— 想改就改，不必顧慮任何上游。

**代價是模板日後的修正不會流過來**，包含安全修正。這是刻意的取捨，理由是：可同步的上游
要能成立，前提是每個專案都遵守「不要改 `shared/` 與組裝層」那條紀律 —— 而多個平行開發的
專案幾乎必然會破壞它。破壞之後，你付了同步機制的全部成本卻拿不到好處（每次拉更新都變成
手動解衝突）。真的有東西需要跨專案更新時，正確的作法是把它做成套件（npm／PyPI），
而不是複製整個 repo。

有需要的話，自己去模板的 CHANGELOG 讀一讀、手動搬需要的修正 —— 那是**你主動的動作**，
不是一條要維護的管線。

## 1. 開案

需要 Docker Desktop、`make`、`openssl`、`uv` 與 Node.js/npm；Node 版本以
[`apps/web/.nvmrc`](apps/web/.nvmrc) 為準。

```bash
git clone <你用 Use this template 開出來的 repo> my-project
cd my-project

make init      # 互動式產生 .env（專案名、port、DB 帳密、各項祕密），不需要網路
make setup     # 驗證 Node 版本，安裝主機端 lint／測試／型別產生工具
make dev       # 啟動開發環境（首次會建置 image，約 2–5 分鐘）
```

**開案先清空 [`CHANGELOG.md`](CHANGELOG.md)**（那是模板的歷史，留在模板 repo 上就好），
從你自己的第一版重新寫；走完這份清單之後再刪掉 `TEMPLATE.md` 本身。

打開 `http://localhost:<SYSTEM_PORT>`（預設 http://localhost:3000）。系統還沒有超級管理者時
會自動落在 `/signup`，填入 `make init` 印出的 `REGISTER_KEY` 建立第一個帳號 ——
**這件事一個部署只能成功一次**。

## 2. 剝除用不到的模組

| 模組 | 處置 |
|---|---|
| `items` | **一定要刪**，它只是範例（連同 `e2e/tests/items.spec.ts`） |
| `realtime`（WebSocket） | 不需要即時推送就整包移除 |
| `push`（Web Push） | 不需要推播通知就整包移除 |

三者的逐項刪除清單在
[`docs/architecture.md`](docs/architecture.md#移除-module)。`realtime` 與 `push`
有反向依賴，要照清單走；`items` 沒有人依賴，直接刪。

刪完依 [`docs/architecture.md`](docs/architecture.md#移除-module) 的收尾順序重產型別，
並執行原始碼、環境變數與文件檢查；剝乾淨與否交給檢查器，不靠眼睛。
模組留下的 CSS 與 token 也算在內 —— `npm run check:tokens` 會把沒人引用的 class
與 token 逐行列出來。

## 3. 決定視覺

模板出廠**只有一份主題**：`default`，深色的灰／靛藍。沒有明暗切換，也沒有導入任何
外部 Design System —— 視覺是開案時要決定的事，兩條路：

**只想換色調**：改 `apps/web/app/themes/default.css` 的右手邊（那 24 個 `--color-*` 是
UI kit 認得的契約，**名字不要動**），需要新的色階就在 `app/tokens/primitives.css` 補。
底色改了要同步 `apps/web/app/manifest.ts` 的 `theme_color`（PWA 吃不到 `var()`，
所以那是唯一一個字面值；`npm run check:tokens` 會比對它與主題底色，漏改會提醒你）。

**要導入自己的 Design System**：**內建的 `default` 留著不動，你的 DS 成為另一份主題** ——
產出放進 `apps/web/app/tokens/vendor/<你的 ds>/`（每一份都要在兩個進入點 `app/layout.tsx`
與 `app/global-error.tsx` 各接一行 import），`app/tokens/primitives.css` 多一條指過去的
調色線，再複製 `app/themes/default.css` 成新主題、改 `DEFAULT_THEME`。
**動手前先讀** [`docs/design-system.md`](docs/design-system.md) 的「導入外部 Design System」：
那一節是完整的流程規範，包含只收哪些檔、落地前要清掉什麼、上游只給亮色時怎麼補、
以及哪幾步沒有檢查器。

兩條路都一樣，改完跑：

```bash
cd apps/web && npm run check:tokens
```

## 4. 改寫 README、授權與安全性政策

`README.md` 現在描述的是模板，**要改寫成你自己專案的**。

模板 README 那句「內部自用，權利保留」是整個 repo 唯一的授權敘述，沒有 `LICENSE` 檔。
改寫時它會被蓋掉，所以**下游專案的授權要由你自己決定並寫上**，
否則你的 repo 會處於完全沒有授權敘述的狀態。

[`.github/SECURITY.md`](.github/SECURITY.md) 也順便看一次。它**刻意沒有寫任何人名或
信箱**，走的是 GitHub 的 repo 相對入口（Security 分頁的「Report a vulnerability」），
所以複製到你的 repo 之後回報會進到**你這裡**，不會誤送到模板維護者 —— 忘了改也不會出事。
要改的只有兩處：「這個 repo 附帶的安全機制」那張清單（你剝掉哪些模組就刪哪幾條），
以及「已知的邊界」（你補上 SBOM 或 image 掃描的話要拿掉對應那條）。
**開關本身要在第 5a 步開**，沒開的話那個回報按鈕不存在。

## 5. 設定 GitHub 那一側

兩件事：分支保護要**設**，CD 要**決定**。

### 5a. repo 設成 public，然後三件事一次做完

**這個模板預設你的 repo 是 public**，因為免費方案上 public 與 private 拿到的東西差很多：

| | public | private（免費方案） |
|---|---|---|
| Actions 分鐘數 | 無限 | 每個帳號每月 2000 分鐘，**所有 repo 共用** |
| ruleset（伺服器端分支保護） | 免費 | 設不了，API 回 403 |
| secret scanning + push protection | 免費 | 要 GitHub Advanced Security（付費） |
| code scanning（CodeQL） | 免費 | 同上 |
| environment 的 required reviewers | 免費 | 設不了 |

**private 不是不能用**，但上面每一列都要各自處理，散落在
[`docs/downstream.md`](docs/downstream.md) 的幾節裡。這裡只講 public 的路。

**先確認歷史裡沒有夾帶過金鑰再轉 public** —— 公開之後就收不回來了，
刪 commit 也沒有用（`.env*` 出廠就在 `.gitignore` 裡，正常流程不會有問題）。

轉成 public 之後做這三件（`origin` 在第 1 步 `git clone` 時就綁好了）：

```bash
gh api --method POST repos/{owner}/{repo}/rulesets --input .github/rulesets/main.json
gh api --method PATCH repos/{owner}/{repo} -f 'security_and_analysis[secret_scanning][status]=enabled' -f 'security_and_analysis[secret_scanning_push_protection][status]=enabled'
```

第三件在網頁上：Settings 的安全那一頁開 **Code scanning**，選 **default setup**、
query suite 選 **Default**。四個開關的意思與為什麼不要 advanced setup，見
[`docs/development.md`](docs/development.md#repo-設定裡的安全掃描)。

第四件是 **Private vulnerability reporting**（同一頁）。
[`.github/SECURITY.md`](.github/SECURITY.md) 要人走 Security 分頁的
「Report a vulnerability」回報，而**那個按鈕要開了這個開關才會出現** ——
沒開的話那份文件指向一個不存在的入口，而回報的人只會改去開公開 issue。
一行也可以：

```bash
gh api --method PUT repos/{owner}/{repo}/private-vulnerability-reporting
```

**ruleset 那一行不是選配的。** `ci.yml` 讓 merge 到 `main` 那一輪不重跑測試，靠的就是它的
strict 政策（分支必須是最新才能 merge）—— 沒匯入的話那個前提不成立，而且**不會有任何紅燈**。
細節見 [`docs/development.md`](docs/development.md#分支保護)。

`make setup` 掛上的 `.githooks/pre-push` 與 CI 的 `pushed-via-pr` job 仍然留著，
它們是第二、三層（本機擋、事後吵），不依賴任何 GitHub 方案。

**團隊超過一個人時記得調高 ruleset 裡的 `required_approving_review_count`**（出廠是 `0`）。

### 5b. 決定要不要用內建的 CD

模板附的 `.github/workflows/` 出廠是**完整的一套**：CI（lint、型別、測試、建置、部署設定
與型別契約的檢查）加上把 image 推上 GHCR 的 `publish` job，以及手動觸發、部署到自架主機的
`deploy.yml`（**手動那一步就是核可閘門**，理由見
[`docs/operations.md`](docs/operations.md#發版與回滾)）。
CI 那幾個 job 直接用就好，**要做決定的是 CD 這一段**：

| 選擇 | 要做什麼 |
|---|---|
| **只用 CI**（部署走 `make prod`，出廠預設的部署方式） | 刪掉 `ci.yml` 的 `publish` job 與 `deploy.yml`，逐項清單見下 |
| **CI + CD 都用**（部署走 `make deploy`） | 照 [`docs/operations.md`](docs/operations.md#registry-模式build-once-deploy-anywhere) 的一次性設定表建好 environment、secrets 與主機憑證 |
| **都不用**（自己接別的 CI 平台） | 整個 `.github/` 刪掉；`make check` 與其餘 `check-*` 在本機仍然可用（`check-ci` 沒有 `ci.yml` 會自己跳過） |

**這件事早點決定比較省事。** `publish` job 在每次 push 到 `main` 都會跑，而它不需要
任何額外設定就會成功（用內建的 `GITHUB_TOKEN` 推 GHCR）。所以「先不管它」不會紅燈，
但會一直往 GHCR 推沒有人用的 image。

主機那一側不必做選擇：`.env` 的 `IMAGE_REGISTRY` 留空就是 `make prod` 就地建置，
那是 `make init` 產生的預設值。**但它管不到 GitHub 那一側** —— 上面那個決定還是要做。

要刪的話逐項清單在 [`docs/downstream.md`](docs/downstream.md#cicd)（那一節同時是日後
反悔想加回來時的對照表）。

## 6. 刪掉這份檔案，並修掉指著它的連結

```bash
git rm TEMPLATE.md
```

**這一步不是刪完就結束。** 有五份文件用 markdown 連結指著這份檔案，刪掉之後
`make check-docs`（在 CI 的 `deploy-config` job 裡）會逐條列出來變紅 ——
症狀會出現在你的第一個 PR 上，而且指向你沒動過的檔案。逐份處理：

| 檔案 | 怎麼修 |
|---|---|
| `README.md` | 第 4 步改寫時一併處理（4 處：抬頭、Quickstart、最短路徑那段、文件地圖那一列） |
| [`AGENTS.md`](AGENTS.md) | 「為什麼不做成可同步的上游，見 TEMPLATE.md」整句刪掉 —— 那是模板的自我說明，對你的專案沒有意義 |
| [`docs/design-system.md`](docs/design-system.md) | 2 處指向 §3「決定視覺」。視覺在第 3 步已經定了，改成敘述你自己的決定，或整句刪掉 |
| [`docs/downstream.md`](docs/downstream.md) | 3 處。這份文件本身要留著（它講的是開案**之後**的決定），只把指回 `TEMPLATE.md` 的連結拆掉 |

還有三處是**純文字提及**（不是連結，所以 `check-docs` 不會紅，但一樣會過期）：
[`docs/extending.md`](docs/extending.md) 與 [`docs/development.md`](docs/development.md)
各有一句「見 `TEMPLATE.md` 第 2 步」指向範例模組，
[`docs/architecture.md`](docs/architecture.md) 的移除模組表格列著 `TEMPLATE.md`。
刪掉範例模組時會一起處理到，這裡順手確認：

```bash
grep -rn "TEMPLATE.md" . --exclude-dir=.git
make check-docs
```

---

## 附錄：只有在改「模板本身」時才適用的規則

如果你**不是**在開案，而是在維護模板這個 repo（判斷方法：`git remote -v`
這個 repo 的 `origin` 就是模板本身）：

- **repo 的 Settings → General 最上面那個 `Template repository` 要打勾。**
  整個開案模式建立在它上面 —— 沒勾的話 GitHub 不會顯示 "Use this template" 按鈕，
  而唯一的替代路徑（clone 之後 `rm -rf .git`）會讓開案的人默默拿到一份帶著模板
  完整歷史的 repo。它跟 ruleset、secret scanning 一樣是 **GitHub 那一側的設定，
  版控裡看不到、也沒有任何檢查器守得到**，所以列在這裡。
  確認方式：`gh api repos/{owner}/{repo} --jq .is_template` 要回 `true`。
- 改動要考慮「所有未來專案都會繼承這個決定」。
- 每次實質改動在 [`CHANGELOG.md`](CHANGELOG.md) 留一筆。
- 必要時升 `apps/api/app/config.py` 的 `APP_VERSION`。開發階段一律 `0.x.x`。

**只有第三條有檢查器在守**（CI 的 `pr-checks` 擋漏寫與寫錯地方，`make check-version`
擋版號對不上）。其餘三條靠自律。
