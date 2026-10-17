# 部署與維運

正式環境的部署、帳號、Session 與安全設定。本機開發見 [`development.md`](development.md)。

## 生產部署

在**部署主機上**：

```bash
git clone <你的 repo> /srv/<專案名> && cd /srv/<專案名>
make init env                      # 只產生 .env；主機的祕密要自己產一份，不要從開發機抄
sudo usermod -aG docker "$USER"    # 不透過 sudo 跑 docker，做完要重新登入
make prod                          # 建置 image 並啟動
```

部署主機只需要 Docker、`make`、`openssl`：`make init env` 不裝 uv 與 Node（那是給
`make check` 用的）。

**升版＝`git pull` 後再 `make prod`**（compose 檔與 nginx 模板是從原始碼 bind mount 的）。

**一台主機只跑一種模式。** dev 與 prod 用同一個 compose 專案名稱與容器名稱（只有資料 volume
分開），所以在 prod 主機上跑 `make dev down` 會停掉正式環境。

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

平常 push 只跑 CI；**在 GitHub 上按 Publish release 才部署**（`.github/workflows/deploy.yml`）：

1. 要部署的 tag 必須是 `v<APP_VERSION>`（`apps/api/app/config.py`），不一致就停。
2. 重跑一次 CI（`ci.yml`），沒過不部署。
3. 建兩份 production image 推到 GHCR：`ghcr.io/<帳號>/<repo>-api:latest` 與 `-web:latest`（全小寫）。
   image 只標 `latest`，執行中的版本看 `APP_VERSION`（設定頁顯示的就是它）。
4. SSH 到主機：`git checkout` 同一個 tag（compose 檔與 nginx 模板是從原始碼 bind mount 的）→
   `make db backup allow-fresh` → 拉 image 並重啟 → `make prod ps` → 清掉被取代的舊 image。

部署前的備份依主機狀態處理：

| 主機狀態 | 處理 |
|---|---|
| 資料庫在跑 | 照常備份 |
| 連資料 volume 都沒有（全新主機） | 沒有東西可備份，略過，直接部署 |
| 有資料 volume，但資料庫沒在跑 | 主機狀態不是預期的，**中止**，先上主機看過 |

清舊 image 只清這個 repo 的（以 `org.opencontainers.image.source` 標籤辨認）、已經沒有容器在用的，
不碰主機上其他專案的 image。

主機上 shell 有 `API_IMAGE` 與 `WEB_IMAGE` 時，`make prod` 改成拉 image、不在主機上建置；
兩個都沒有就和以前一樣在本機建置，所以手動 `make prod` 照常可用。

**首次設定**：主機上**不必**先把服務跑起來，也不在主機上建置 image。照上一節的指令做到
`make init env` 與 `docker` 群組就停（**不要跑 `make prod`**），其餘交給第一次 Publish：

- [ ] 主機的 repo 要能 `git fetch`：私有 repo 在 GitHub 的 Deploy keys 加一把**唯讀**的 key
- [ ] 主機上開一個部署用的帳號，加進 `docker` 群組，能讀寫 repo 目錄；把它的公鑰放進
      `~/.ssh/authorized_keys`
- [ ] repo 的 Settings → Environments 建立 `production`，加入 secrets：

  | Secret | 內容 |
  |---|---|
  | `DEPLOY_HOST` | 主機位址 |
  | `DEPLOY_PORT` | SSH port，可省略（預設 22） |
  | `DEPLOY_USER` | 部署帳號 |
  | `DEPLOY_PATH` | 主機上的 repo 目錄，例如 `/srv/<專案名>` |
  | `DEPLOY_SSH_KEY` | 部署帳號的**私鑰**（只給 CD 用的那一把） |
  | `DEPLOY_KNOWN_HOSTS` | 主機指紋：`ssh-keyscan -p <port> <主機>` 的輸出，**自己比對過**再貼 |

- [ ] repo 的 Settings → Variables 加 `UPLOAD_SIZE_LIMIT`，與主機 `.env` 的**同一個值**
      （會在 build 時烤進 image，不一致時 web 開機就結束）
- [ ] 第一次推上去之後，到 GHCR 的 package 設定確認 Visibility：image 裡有完整的程式碼（但沒有機密），
      **私有 repo 要設 Private**；公開 repo 的 image 內容等於原始碼，設 Public 也可以，而且免費。
      **改成 Public 之後就改不回 Private**
- [ ] 想要「按下 Publish 之後再核准一次」：在 `production` environment 開 Required reviewers

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

主機拉 image 用的是那次 job 的 `GITHUB_TOKEN`，job 結束就失效，主機不存長期的 registry 憑證；
部署結束時會 `docker logout ghcr.io`，主機上手動登入的 GHCR 也會一起登出。

**發版**：`make release <版號>` → 看過 diff 後 commit、push → 在 GitHub 建 release，tag 填 `v<版號>`，按 Publish。

跟 git tag 對齊的版號只有兩處：後端的 `APP_VERSION` 與 CHANGELOG 的版本段落；只改了 api 或 web
也一樣升這一個。前端顯示的版號經 `GET /api/system/version` 取自 `APP_VERSION`。
`make release` 會改 `APP_VERSION`，並把 CHANGELOG 的 `[Unreleased]` 改成這個版號；不要手動改，
`make check` 會擋下兩者不一致（`apps/api/tests/test_version.py`）。

其餘的版號**刻意不跟發版**，有實際變更時才改，git 上的 diff 才代表真的有東西變了：

| 版號 | 什麼時候改 |
|---|---|
| `pyproject.toml`、`uv.lock`、`package.json`、`package-lock.json` 的專案版號 | 那個套件本身有變更時才改，不跟發版 |
| OpenAPI 的 `info.version`（`app/config.py` 的 `CONTRACT_VERSION`） | 契約有**破壞性**變更時手動 +1；一般變更看 `contracts/openapi.json` 的 diff |

**重新部署某個版本（回滾）**：Actions → Deploy → **Run workflow**，branch 選 `main`，填一個已經存在的 tag
（例如上一版的 `v0.1.0`）。它走同一套流程（版號檢查、CI、從那個 tag 重建 `latest`、備份、部署），只是不建新的 tag；
發新版仍然要走 Publish release。**migration 不會倒退**：新版改過
資料表的話，舊程式可能讀不了新結構，這時要用部署前的備份 `make db restore`（會失去備份之後的資料）。

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
make db backup                  # 備份到 ./backups/<資料庫>_<時間>.dump
make db restore                 # 列出 ./backups/ 的備份，選一個並確認後還原
make db restore backups/x.dump  # 直接指定檔案
```

還原會**取代備份裡有的資料表**（`pg_restore --clean`）；備份之後才新建的表不會被刪掉。
`backups/` 只在這台機器上，**正式環境要自己安排排程與異地保存**，並定期實際還原一次 ——
沒有演練過的備份等於沒有備份。
