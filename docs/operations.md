# 部署與維運

正式環境的部署、帳號、Session 與安全設定。本機開發見 [`development.md`](development.md)。

## 生產部署

在**部署主機上**：

```bash
git clone <你的 repo> /srv/<專案名> && cd /srv/<專案名>
sudo usermod -aG docker "$USER"    # 不透過 sudo 跑 docker，做完要重新登入
make init env                      # 只產生 .env；主機的祕密要自己產一份，不要從開發機抄
make prod                          # 建置 image 並啟動
```

部署主機只需要 Docker、`make`、`openssl`：`make init env` 不裝 uv 與 Node（那是給
`make check` 用的）。

**升版＝`git pull` 後再 `make prod`**（compose 檔與 nginx 模板是從原始碼 bind mount 的）。

**一個目錄只跑一種模式。** dev 與 prod 用同一個 compose 專案名稱與容器名稱（只有資料 volume
分開），所以在 prod 的目錄跑 `make dev down` 會停掉正式環境。同一台主機要跑多套，就各用一個目錄，
`.env` 的 `COMPOSE_PROJECT_NAME` 與 `SYSTEM_PORT` 不重複（見〈[新增一套系統](#新增一套系統)〉）。

啟動順序是 `postgres → migrate → api → web → nginx`。api 等 migration **成功結束**才啟動，
所以 migration 失敗時不會有服務對外開放。沒有待執行的 migration 時 `migrate` 直接結束；
環境起著時也可以用 `make db migrate` 單獨套用。

prod overlay 比 dev 多了 **log 上限**與**記憶體上限**（api、web 各 512M，postgres 1G）。
api 週期性重啟時，先懷疑記憶體上限。

上線前確認：

- [ ] HTTPS 由前面的 reverse proxy 或 load balancer 處理；**多一層 proxy 時要調整取 IP 的方式**，
      見〈[用戶端 IP 與限流](#用戶端-ip-與限流)〉
- [ ] 對外只開 nginx 的 port
- [ ] `.env` 的密碼、`JWT_SECRET_KEY`、`REGISTER_KEY` 都是這台主機自己產的
- [ ] 備份排程與異地保存，並做過一次還原演練
- [ ] 依平台補上監控與錯誤追蹤（見下一節）
- [ ] 使用者知道忘記密碼要找誰（沒有寄信重設的功能）

要改成 CI 建 image、主機只拉 image，見下一節〈自動部署〉。

### 自動部署

平常 push 只跑 CI；**在 GitHub 上發布 release 才部署**（`.github/workflows/deploy.yml`）。

**一個 GitHub environment 就是一套系統**，名稱的前綴決定它屬於哪一組。
組名是名稱第一個 `-` 之前的部分，不分大小寫：

| Environment | 組 |
|---|---|
| `production`、`production-system-a`、`production-system-b` | production |
| `staging`、`staging-system-a` | staging |

**一組裡的系統一起更新、一起回滾**，永遠跑同一版。新增一套系統只要建一個符合命名的
environment（見下方〈新增一套系統〉），workflow 不用改。`productionx` 這種只是開頭相同、
沒有 `-` 分隔的名稱**不算** production 組。

要部署哪幾組**由 repo 的 Variables 決定**（Settings → Secrets and variables → Actions → Variables），
多組用空格分開，例如 `production staging`：

| 觸發 | 部署哪些組 |
|---|---|
| 發布 release 時勾選 **Set as a pre-release** | `PRE_RELEASE_TARGETS` 的組 |
| 發布正式版（沒有勾 pre-release），或把 pre-release 改成正式版 | `PUBLISH_TARGETS` 的組 |
| Actions → Deploy → Run workflow | `target` 填的組（多組用空格分開），`tag` 必須已經存在 |

- **兩個 Variable 各自判斷**：發布的是哪一種，就只看對應的那一個。
- **沒設定或空白就失敗**，這次一套都不部署，執行頁面上寫明是哪一個 Variable 沒設。
- **列出的組有任何一個找不到 environment**（例如打錯字），整次都不部署，並列出現有的組。
- **沒列出的組不會更新**。Summary 會列出「這次沒有部署的組」，要補就對同一個 tag 按 Run workflow。

先行測試的流程：發布 `v0.0.3` 時勾 pre-release → `PRE_RELEASE_TARGETS` 的組（例如 `canary`）先更新 →
觀察沒問題後，編輯這個 release、取消勾選 pre-release → `PUBLISH_TARGETS` 的組更新。
**兩次用的是同一個 tag**，不用改版號。驗證失敗就不要轉成正式版，修好後發下一個版號。

每次部署的流程：

1. 要部署的 tag 必須是 `v<APP_VERSION>`（`apps/api/app/config.py`），不一致就停。
2. 列出 repo 裡屬於這些組的 environment；有任何一組找不到就停，並列出現有的組。
3. 重跑一次 CI（`ci.yml`），沒過不部署。
4. 建兩份 production image 推到 GHCR：`ghcr.io/<帳號>/<repo>-api:<組名>` 與 `-web:<組名>`（全小寫）。
   只建一次，這次部署的每一組各標一個組名。image 只標組名，執行中的版本看 `APP_VERSION`
   （設定頁顯示的就是它）；不同組用不同標籤，先行測試的組部署新版時不會蓋掉其他組的 image。
5. **一次一套**依序部署，每套是一個獨立的 job（`deploy (<environment>)`）：檢查 secrets →
   SSH 到主機 → `make db backup allow-fresh`（在 checkout 之前，備份檔才會標上線上那一版的版號）→
   `git checkout` 同一個 tag（compose 檔與 nginx 模板是從原始碼 bind mount 的）→ 拉 image 並重啟 →
   `make prod ps` → 清掉被取代的舊 image。
   **一套失敗不會中斷其他套**。
6. 執行頁面的 **Summary** 列出每套的結果與失敗的步驟，以及這次沒有部署的組。失敗的那套點進它的
   job 看 log，修好之後按 **Re-run failed jobs**，只會重跑失敗的那幾套。

一次部署可能包含好幾組，所以**整個 repo 的部署共用一個排隊群組**，依序跑。
GitHub 同一個排隊群組最多「一個在跑、一個在等」，再排進第三個時，**原本在等的那個會被取消**。

部署前的備份依主機狀態處理：

| 主機狀態 | 處理 |
|---|---|
| 資料庫在跑 | 照常備份 |
| 連資料 volume 都沒有（全新主機） | 沒有東西可備份，略過，直接部署 |
| 有資料 volume，但資料庫沒在跑 | 主機狀態不是預期的，**中止**，先上主機看過 |

清舊 image 只清這個 repo 的（以 `org.opencontainers.image.source` 標籤辨認）、已經沒有容器在用的，
不碰主機上其他專案的 image，**也從不碰 volume**。同一台主機上其他套系統還在用的舊 image 不算沒人用，
輪到它們更新之後才會被清掉。

主機上 shell 有 `API_IMAGE` 與 `WEB_IMAGE` 時，`make prod` 改成拉 image、不在主機上建置；
兩個都沒有就和以前一樣在本機建置，所以手動 `make prod` 照常可用。

**首次設定**：主機上**不必**先把服務跑起來，也不在主機上建置 image。照上一節的指令做到
`docker` 群組與 `make init env` 就停（**不要跑 `make prod`**），其餘交給第一次發布：

- [ ] 主機的 repo 要能 `git fetch`：私有 repo 在 GitHub 的 Deploy keys 加一把**唯讀**的 key
- [ ] 主機上開一個部署用的帳號，加進 `docker` 群組，能讀寫 repo 目錄；把它的公鑰放進
      `~/.ssh/authorized_keys`
- [ ] repo 的 Settings → Environments 建立 `production`（或 `production-<系統名>`），加入 secrets：

  | Secret | 內容 |
  |---|---|
  | `DEPLOY_HOST` | 主機位址 |
  | `DEPLOY_PORT` | SSH port，可省略（預設 22） |
  | `DEPLOY_USER` | 部署帳號 |
  | `DEPLOY_PATH` | 主機上的 repo 目錄，例如 `/srv/<專案名>` |
  | `DEPLOY_SSH_KEY` | 部署帳號的**私鑰**（只給 CD 用的那一把） |
  | `DEPLOY_KNOWN_HOSTS` | 主機指紋：`ssh-keyscan -p <port> <主機>` 的輸出，**自己比對過**再貼 |

  缺了必填的 secret 時，那套系統在連上主機之前就會失敗，log 裡寫明缺了哪幾個。
- [ ] 在 environment 的 **Deployment branches and tags** 選 **Selected branches and tags**，
      按 Add deployment branch or tag rule 加兩條：

  | Ref type | Name pattern | 給誰用 |
  |---|---|---|
  | Tag | `v*` | 發布 release（這時的 ref 是 tag） |
  | Branch | `main` | Run workflow（這時的 ref 是 `main`，要部署的版本由 `tag` 欄位決定） |

  **這兩條才是真正的安全邊界**：Run workflow 可以選任何 branch 來跑，選到的 branch 上的
  `deploy.yml` 就是會執行的那份，workflow 裡「只能從 main 執行」的檢查可以在那個 branch 上被刪掉；
  environment 的規則由 GitHub 判斷，其他 ref 拿不到這套系統的 secrets。少了 `main` 那條，
  回滾與部署到其他組會在 deploy job 被 GitHub 擋下（environment protection rules）。
  `main` 要有 ruleset（見 [`development.md`](development.md)），它上面的 `deploy.yml` 才一定經過 PR。
- [ ] repo 的 Settings → Variables 加 `UPLOAD_SIZE_LIMIT`，與主機 `.env` 的**同一個值**
      （會在 build 時烤進 image，不一致時 web 開機就結束）。它放在 repo 層級，因為同一份 image
      給組裡每套系統用，**每套系統的 `.env` 都要是這個值**
- [ ] 第一次推上去之後，到 GHCR 的 package 設定確認 Visibility：image 裡有完整的程式碼（但沒有機密），
      **私有 repo 要設 Private**；公開 repo 的 image 內容等於原始碼，設 Public 也可以，而且免費。
      **改成 Public 之後就改不回 Private**
- [ ] repo 的 Settings → Variables 加 `PUBLISH_TARGETS`（例如 `production`）；要用 pre-release
      先行測試時再加 `PRE_RELEASE_TARGETS`（例如 `canary`）
- [ ] 想要「發布之後再核准一次」：在 environment 開 Required reviewers
      （每個 environment 各自核准，一組有三套就要核准三次）

第一次部署完成後，**由最初使用系統的人**進站建立超級管理者（自動落在 `/signup`，填 `.env` 的
`REGISTER_KEY`，見〈[第一個超級管理者](#第一個超級管理者)〉）。這是系統初始化的一環，部署流程刻意不代建。

主機以前手動 `make prod` 建過 image 的話，那些 image 與建置快取 CD 用不到，
部署成功後可以清掉（`<專案名>` 是 `.env` 的 `COMPOSE_PROJECT_NAME`）：

```bash
docker image rm <專案名>-api:latest <專案名>-web:latest
```

```bash
docker builder prune
```

從只標 `latest` 的版本升上來時，主機上舊的 `ghcr.io/<帳號>/<repo>-api:latest` 與 `-web:latest`
還帶著標籤，不會被自動清掉；第一次部署成功後手動 `docker image rm` 掉即可。

主機拉 image 用的是那次 job 的 `GITHUB_TOKEN`，job 結束就失效，主機不存長期的 registry 憑證。
登入資訊寫在每次部署自己的暫存目錄（`DOCKER_CONFIG`），結束就刪掉，**不碰部署帳號的 `~/.docker`**：
同一個帳號跑多套系統時不會互相登出，主機上手動登入的 GHCR 也不受影響。

#### 新增一套系統

同一組的多套系統可以在不同主機，也可以在同一台主機的不同目錄：

1. 主機上 clone 到新的目錄，例如 `/srv/system-b`，`make init env`。`.env` 的
   `COMPOSE_PROJECT_NAME`、`SYSTEM_PORT` **不可以與同主機的其他套重複**（容器、volume、
   network 都以前者為前綴），`UPLOAD_SIZE_LIMIT` 與 repo Variable 相同。
2. GitHub 建 environment，例如 `production-system-b`，照〈首次設定〉填 secrets，並加上同樣兩條
   部署規則（tag `v*`、branch `main`）；`DEPLOY_PATH` 指向新目錄，同主機的其他 secrets 與其他套相同。
3. 確認它的組列在 `PUBLISH_TARGETS` 或 `PRE_RELEASE_TARGETS`（是新的組才需要加）；下一次發布
   （或對目前的 tag 按 Run workflow）就會部署到它。
4. 同主機有多套時，HTTPS 與網域由主機上的 reverse proxy 依網域轉到各套的 `SYSTEM_PORT`。

#### 停用一套系統

在主機上停掉（`make prod down`，資料留在 volume）之後，下一次部署到這一組時，**這套會在備份那一步中止**
（有資料 volume 但資料庫沒在跑），不會被自動重新啟動，其他套照常更新，只是這次部署會標成失敗。
要長期停用就刪掉或改名它的 environment（改成不屬於任何部署組的名稱），它就不會再被納入。

停用期間，它的舊 image 可能在其他套更新之後被清掉；資料不受影響。重新啟用時對目前的 tag 按一次
Run workflow 就會拉回來。

**發版**：`make release <版號>` → 看過 diff 後 commit、push → 在 GitHub 建 release，tag 填 `v<版號>`，按 Publish
（要先行測試就勾 pre-release，見上方〈自動部署〉）。

跟 git tag 對齊的版號只有兩處：後端的 `APP_VERSION` 與 CHANGELOG 的版本段落；只改了 api 或 web
也一樣升這一個。前端顯示的版號經 `GET /api/system/version` 取自 `APP_VERSION`。
`make release` 會改 `APP_VERSION`，並把 CHANGELOG 的 `[Unreleased]` 改成這個版號；不要手動改，
`make check` 會擋下兩者不一致（`apps/api/tests/test_version.py`）。

其餘的版號**刻意不跟發版**，有實際變更時才改，git 上的 diff 才代表真的有東西變了：

| 版號 | 什麼時候改 |
|---|---|
| `pyproject.toml`、`uv.lock`、`package.json`、`package-lock.json` 的專案版號 | 那個套件本身有變更時才改，不跟發版 |
| OpenAPI 的 `info.version`（`app/config.py` 的 `CONTRACT_VERSION`） | 契約有**破壞性**變更時手動 +1；一般變更看 `contracts/openapi.json` 的 diff |

**部署到其他組，或重新部署某個版本（回滾）**：Actions → Deploy → **Run workflow**，branch 選 `main`，
填一個已經存在的 tag（例如上一版的 `v0.1.0`）與 `target`（要部署的組，多組用空格分開）。
它走同一套流程（版號檢查、CI、從那個 tag 重建這一組的 image、逐套備份與部署），只是不建新的 tag；
發新版仍然要走發布 release。回滾一樣是**整組一起**。也可以用指令觸發：

```bash
gh workflow run deploy.yml --ref main -f tag=v0.1.0 -f target="production staging"
```

**migration 不會倒退**：新版改過
資料表的話，舊程式可能讀不了新結構，這時要用部署前的備份 `make db restore`（會失去備份之後的資料）。
部署前的備份標的是當時線上的版本，所以回滾到 `v0.1.0` 後，`make version` 是 `v0.1.0`，
`make db restore` 列出的就是 `v0.1.0` 時留下的備份。

### 可觀測性只到 stdout

- **有**：後端寫到 stdout 的請求紀錄（方法、路徑、狀態碼、耗時，**不含 query string**），以及
  web、api、postgres 的 Docker healthcheck。
- **有** request id：每行紀錄開頭的 `[xxxxxxxx]` 由 nginx 產生，經 Next 傳到後端並回寫到回應標頭，
  同一次操作在三個服務的 log 裡是同一個 id。
- **沒有**：結構化 log、錯誤追蹤（Sentry 之類）、指標。做法依部署平台而定，**上線前自己補上**。

## 帳號

### 第一個超級管理者

系統還沒有超級管理者時，進站會自動落在 `/signup`，填 `.env` 的 `REGISTER_KEY` 建立。
**一個部署只能成功一次**，之後 `/signup` 永久關閉，`REGISTER_KEY` 可以從 `.env` 清空。
其餘帳號由超級管理者在「使用者管理」頁面建立。

### 第二個超級管理者，或唯一的超管失聯

```bash
make db superuser
```

互動式輸入暱稱、帳號、密碼（密碼不回顯），可以重複執行。後台只開放給超級管理者，
需要另一位能管理使用者與角色的人，就是走這條路。

### 角色

預設只有一個內建角色 `super_admin`（權限 `*`，涵蓋所有操作與日後新增的權限）。
它**不能經由 API 指派**，只能由上面兩種方式產生。新建的使用者沒指定角色時沒有任何權限；
需要 `member` 之類的預設角色，在 `RoleTable.seed_data` 新增（見
[`extending.md`](extending.md#初始資料seed)）。系統角色（有 `code` 的）的權限、名稱與啟用狀態
都由模板擁有，不能經由 API 修改，畫面上的名稱依 `code` 查前端字典。

### 後台只開放給超級管理者

使用者與角色的管理（後台）只有超級管理者進得去：前端的 `admin/layout.tsx` 只看是不是
超級管理者，後端這些端點一律要求 `Permission.ALL`。角色上的權限是給**一般帳號**的業務功能用的，
沒有任何一個權限能打開後台。

一般帳號對自己帳號的操作（改暱稱、改密碼、語系）集中在設定頁，不需要任何權限。

即使是超級管理者也不能做的事：停用自己、停用超級管理者、指派超級管理者角色、把 `*` 放進一般角色、
修改系統角色。

## Session

### 撤銷

| | 存在哪 | 作用範圍 | 怎麼觸發 |
|---|---|---|---|
| `TOKEN_VERSION` | `.env` | **所有人** | 手動 +1 後重啟，例如 `JWT_SECRET_KEY` 外洩時 |
| `auth_version` | `users` 資料表 | **單一使用者** | 換密碼（管理者重設或自己改）或登出時自動 +1 |

`auth_version` +1 只影響那一個帳號，其他使用者的 token 照常有效：

- 使用者自己改密碼：其他裝置全部登出，這一台會拿到新 token 繼續用。
- 管理者重設密碼：那個人的所有裝置都登出。
- 登出：這個帳號的**所有裝置**一起登出，不只是按下登出的那一台。token 是無狀態的，只刪
  cookie 的話，已經被複製出去的 token 到期前仍然有效，所以登出走的是同一條撤銷路徑。

### 不會續期

沒有 refresh token，也沒有「有在操作就延長」。`EXPIRE_HOURS` 是**登入後多久一定要重新登入**
的硬上限，跟有沒有在用無關 —— 設 8 小時的話，早上九點登入的人下午五點會被導回登入頁。

### 密碼

- 記得舊密碼 → 自己在設定頁改。
- 忘記密碼 → 請超級管理者在後台重設（超級管理者全部失聯時用 `make db superuser` 另建一個）。
  模板沒有 email，所以沒有寄重設連結。

## 用戶端 IP 與限流

登入與註冊以用戶端 IP 限流（`shared/http/rate_limit.py`，數字在 `modules/users/router.py`）。
後端只讀 `X-Real-IP`，**前提是 nginx 是最外層**：nginx 以 `$remote_addr` 覆寫這個標頭，
`apps/api/tests/test_nginx_templates.py` 確保每個 location 都有覆寫。

**nginx 前面還有一層 proxy（LB、CDN）時**，`$remote_addr` 會變成那層 proxy 的位址，
所有使用者共用同一個限流額度 —— 一個人打爆，全站被鎖。這時在
`infra/nginx/default.conf.template` 的 server 區塊加上：

```nginx
set_real_ip_from  10.0.0.0/8;   # 換成你的 LB／CDN 實際的 CIDR，不要填 0.0.0.0/0
real_ip_header    X-Forwarded-For;
real_ip_recursive on;
```

### 單一行程，不能直接加副本

API 是**單一 Python 行程**（沒有 workers，compose 也沒有 replica）。限流的計數存在行程記憶體裡，
加 workers 或副本會讓允許次數直接變成 N 倍，而且沒有任何症狀。要水平擴充時，**先**把
`RateLimiter` 的計數換成 Redis，**再**加副本。

## 備份與還原

```bash
make version                    # 目前的版本，例如 v0.0.2
make db backup                  # 備份到 ./backups/<專案>_v<版號>_<日期>_<時間>.dump
make db restore                 # 列出目前版本的備份，選一個並確認後還原
make db restore backups/x.dump  # 直接指定檔案（版本必須與 make version 一致）
```

清單只列出與 `make version` 一致的備份，新到舊，例如 `1) v0.0.2 2026-10-17 08:35:53`。
**還原只接受目前版本的備份**：別版的資料表結構可能跟目前的程式對不上，要還原別版的備份就先部署回那一版。
檔名沒有版號的舊備份不會列出，真的要用時自己改名成上面的格式。

還原會**取代備份裡有的資料表**（`pg_restore --clean`）；備份之後才新建的表不會被刪掉。
`backups/` 只在這台機器上，**正式環境要自己安排排程與異地保存**，並定期實際還原一次 ——
沒有演練過的備份等於沒有備份。
