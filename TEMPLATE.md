# 開案指南（**導入完成後刪掉這一份**）

這份檔案只在「把模板變成你的專案」這段期間有用。走完下面的清單就
`git rm TEMPLATE.md`——留著它只會讓後續開發的人以為自己還在模板裡。

長期有效的規則不在這裡：開發規則見 [`AGENTS.md`](AGENTS.md)，
同步紀律見 [`docs/downstream.md`](docs/downstream.md)。

## 1. 開案

需要 Docker Desktop、`make`、`openssl`、`uv` 與 Node.js/npm；Node 版本以
[`apps/web/.nvmrc`](apps/web/.nvmrc) 為準。

```bash
git clone <模板位置> my-project
cd my-project

# 把模板留成可持續拉更新的上游
git remote rename origin template

make init      # 互動式產生 .env（專案名、port、DB 帳密、各項祕密），不需要網路
make setup     # 驗證 Node 版本，安裝主機端 lint／測試／型別產生工具
make remote    # 綁定你自己的儲存庫（名稱填 origin）；只在本機試跑可以略過
make dev       # 啟動開發環境（首次會建置 image，約 2–5 分鐘）
```

`<模板位置>` 由提供模板的人告知，git URL 或本機路徑都可以。

**不要 `rm -rf .git` 重開一段歷史。** 保留 clone 下來的歷史是同步流程唯一的前提，
理由見 [`docs/downstream.md`](docs/downstream.md#拉模板的更新)。`make remote` 會順便檢查並提醒你。

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

## 4. 改寫 README 與授權

`README.md` 現在描述的是模板，**要改寫成你自己專案的**。

模板 README 那句「內部自用，權利保留」是整個 repo 唯一的授權敘述，沒有 `LICENSE` 檔。
改寫時它會被蓋掉，所以**下游專案的授權要由你自己決定並寫上**，
否則你的 repo 會處於完全沒有授權敘述的狀態。

## 5. 設定 GitHub 那一側

兩件事：分支保護要**設**，CD 要**決定**。

### 5a. 分支保護

**多數人這一步不用做任何事。** `make setup` 已經掛上 `.githooks/pre-push`（擋直接 push 到
`main`、force push 與刪除），CI 的 `pushed-via-pr` job 會把漏網的吵出來。這兩層不依賴
任何 GitHub 方案，但**也都不是強制** —— 細節與限制見
[`docs/development.md`](docs/development.md#分支保護)。

要真正的伺服器端強制的話，那是 GitHub 的付費功能（**private repo 在免費方案上設不了**，
API 直接回 403）。你的 repo 是 public 或付費方案時，綁好 `origin`（第 1 步的 `make remote`）
之後匯入模板附的 ruleset 就有了：

```bash
gh api --method POST repos/{owner}/{repo}/rulesets --input .github/rulesets/main.json
```

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

**這件事要在第一次 push 到 `main` 之前決定，不是「以後想部署再說」。**
`publish` job 在每次 push 到 `main` 都會跑，而它第一步就檢查 repository secret
`NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` 在不在 —— 沒設就是紅燈，而那支 secret 只有
registry 模式需要（理由見 `operations.md` 的「兩個 build 期值」）。
所以「先不管它」的結果是每次推程式碼都收到一封失敗通知。

主機那一側不必做選擇：`.env` 的 `IMAGE_REGISTRY` 留空就是 `make prod` 就地建置，
那是 `make init` 產生的預設值。**但它管不到 GitHub 那一側** —— 上面那個決定還是要做。

要刪的話逐項清單在 [`docs/downstream.md`](docs/downstream.md#cicd)（那一節同時是日後
反悔想加回來時的對照表）。**先刪完再走下一步** —— 下一步的「就此分家」會把
`docs/downstream.md` 一起刪掉。

## 6. 決定要不要繼續跟上游

- **要繼續拉模板更新**：留著 `template` 這個 remote 與 `docs/downstream.md`，
  之後照那份文件的紀律走（重點：不要改 `shared/` 與組裝層）。
- **就此分家**：`git remote remove template`，並刪掉 `docs/downstream.md`
  與 `AGENTS.md` 裡指向它的那一行。分家之後 `shared/` 就是你自己的了，隨便改。

## 7. 刪掉這份檔案

```bash
git rm TEMPLATE.md
```

順手確認沒有其他地方還指著它：`grep -rn "TEMPLATE.md" . --exclude-dir=.git`。

---

## 附錄：只有在改「模板本身」時才適用的規則

如果你**不是**在開案，而是在維護模板這個 repo（判斷方法：`git remote -v`
**沒有**一個叫 `template` 的遠端，因為你就是上游）：

- 改動要考慮「所有未來專案都會繼承這個決定」。
- 每次實質改動在 [`CHANGELOG.template.md`](CHANGELOG.template.md) 留一筆，開頭帶同步影響標記
  （`[同步:無]`／`[同步:要動手]`／`[同步:破壞性]`）並註明**下游同步時需要做什麼**。
  根目錄的 `CHANGELOG.md` 是留給下游專案的，模板不碰它。
- 必要時升 `apps/api/app/config.py` 的 `APP_VERSION`。開發階段一律 `0.x.x`。

**只有第二條有檢查器在守**（CI 的 `changelog` job 擋漏寫與寫錯地方，`make check-version`
擋漏標記與版號對不上）。第一條與第三條靠自律。
