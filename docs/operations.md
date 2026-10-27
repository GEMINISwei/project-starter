# 部署與維運

正式環境的部署、主機設定、備份與救援。系統功能怎麼運作見 [`features/`](features/README.md)，本機開發見 [`development.md`](development.md)。

## 生產部署

在**部署主機上**：

```bash
git clone <你的 repo> /srv/<專案名> && cd /srv/<專案名>
sudo usermod -aG docker "$USER"    # 不透過 sudo 跑 docker，做完要重新登入
make init prod                     # 只產生 .env（MODE=production）；主機的祕密要自己產一份，不要從開發機抄
git checkout v<版號>               # 正式環境只從發版的 tag 啟動
make start                         # 建置 image 並啟動
```

部署主機只需要 Docker、`make`、`openssl`：`make init prod` 不裝 uv 與 Node（那是給
`make check` 用的）。

**升版＝`git fetch --tags && git checkout v<版號>` 後再 `make start`**（compose 檔與 nginx 模板是
從原始碼 bind mount 的）。`MODE=production` 時 `make start` 只認停在 `v<APP_VERSION>` tag 上的
checkout：在主機上 `git pull` 了 main 再啟動，等於上線一份沒發版、沒經過 CI 的程式碼。

nginx 的模板（`infra/nginx/`）有變時，`make start` 會重建 nginx，沒變就不動。bind mount 的內容變了，
compose 本身看不出來，所以由 `scripts/lib/compose.sh` 把內容的雜湊放進 nginx 的 label。
重建之前會先用一次性的容器跑 `nginx -t`；**模板寫錯時 `make start` 在啟動任何服務之前就失敗**，
線上的 nginx 維持原樣。

**`.env` 的 `MODE` 決定這個目錄是哪種環境**（`make init prod` 寫入 `production`），一個目錄只會有
一種。`MODE=production` 時這些指令會直接拒絕，防的是手誤，不是權限控制（能上主機的人照樣可以改 `.env`）：

| 被擋的指令 | 原因 |
|---|---|
| `make db reset` | 清空資料 |
| `make db migrate` | migration 由 `make start` 的 migrate 服務套用；這條路徑不會先備份 |
| `make db migration`、`make check`、`make gen-types`、`make release`、`make init dev` | 開發機的工作 |

`make services down` 在正式環境要先確認（資料留在 volume，但服務會停）。

`make services restart` 原地重啟現有的容器（migrate 除外），在正式環境也要先確認。它不重建容器、不拉也不建 image，
所以主機上不必知道 image 名稱、不必登入 GHCR，跑的是本機建置的還是 registry 拉的都照原樣。
**它不套用任何變更**：`.env`、compose、image 變了要用 `make start`；容器已經 `down` 掉時也只能 `make start`。
nginx 模板改了也用 `make start`：它會先跑 `nginx -t` 再重建 nginx。restart 雖然也會重新展開模板，
但**不會先檢查**，模板寫錯時 nginx 起不來，整個站就停了。

`make services` 會列出這個專案的 volume（以 compose 的專案標籤篩選），名稱不是 `<專案>_<MODE>_`
開頭的標 `← Not Matched`：另一種模式留下的，或改過命名之前的舊 volume，目前的 `MODE` 用不到，
也不會自己消失。只標註不刪除，確定不要了再自己 `docker volume rm`。各 volume 的容量看
`make services volumes`（要掃過整台主機的 volume，所以不放在 `make services` 裡）。

同一台主機要跑多套，就各用一個目錄，`.env` 的 `COMPOSE_PROJECT_NAME` 與 `SYSTEM_PORT` 不重複
（見〈[新增一套系統](#新增一套系統)〉）。

`make start` 先用要上線的 image **單獨跑一次 migrate**，成功才切換服務：失敗就停在這裡，線上的服務
維持原狀。migrate 做兩件事：`alembic upgrade head`，接著補齊初始資料（seed，見
[`extending.md`](extending.md#初始資料seed)）。migration 失敗時整個撤回（PostgreSQL 的 DDL 在交易裡）；
seed 失敗時結構已經升上去了，服務一樣不切換，修好之後重跑即可（seed 可以重複執行）。之後的啟動順序是
`postgres → migrate → api → web → nginx`，這時 `migrate` 再跑一次，沒有待執行的 migration、seed 也已經是最新的。

**每次部署都會短暫中斷服務**：部署前的備份期間 nginx 是停的（資料越多越久，見
〈[備份與還原](#備份與還原)〉），`make start` 重建容器後也要等 healthcheck 通過，nginx 才會接回流量。
所以要挑離峰時段部署。零停機（新版起來才切流量）的前提是 api 能同時跑兩份，目前做不到，見
〈[單一行程，不能直接加副本](#單一行程不能直接加副本)〉與 [ADR 0004](decisions/0004-downtime-deploys.md)。

prod overlay 比 dev 多了 **log 上限**與**記憶體上限**（api、web 各 512M，postgres 1G）。
api 週期性重啟時，先懷疑記憶體上限。

上線前確認：

- [ ] 主機的 reverse proxy 照 [`infra/host-nginx/example.conf`](../infra/host-nginx/example.conf)
      設定（HTTPS、轉送標頭、上傳上限），見〈[主機的 reverse proxy](#主機的-reverse-proxy)〉
- [ ] 從**另一台機器**連 `http://<主機>:<SYSTEM_PORT>` 要連不上（compose 只綁 127.0.0.1）
- [ ] `.env` 的密碼、`JWT_SECRET_KEY` 都是這台主機自己產的
- [ ] 備份排程與異地保存，並做過一次還原演練
- [ ] 確認只有 log、沒有錯誤追蹤與告警是可以接受的（見〈[可觀測性只到 stdout](#可觀測性只到-stdout)〉）
- [ ] 使用者知道忘記密碼要找誰（沒有寄信重設的功能，見 [帳號、角色與密碼](features/accounts-roles.md#密碼)）

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
- **沒列出的組不會更新**。執行頁面的 Summary 會列出「這次沒有部署的組」，要補就對同一個 tag 按 Run workflow。

先行測試的流程：發布 `v0.0.3` 時勾 pre-release → `PRE_RELEASE_TARGETS` 的組（例如 `canary`）先更新 →
觀察沒問題後，編輯這個 release、取消勾選 pre-release → `PUBLISH_TARGETS` 的組更新。
**兩次用的是同一個 tag**，不用改版號。驗證失敗就不要轉成正式版，修好後發下一個版號。

每次部署的流程：

1. 要部署的 tag 必須是 `v<APP_VERSION>`（`apps/api/app/config.py`），不一致就停。
2. 列出 repo 裡屬於這些組的 environment；有任何一組找不到就停，並列出現有的組。
3. 重跑一次 CI（`ci.yml`），沒過不部署。同時逐套讀主機資料庫的 migration revision
   （`migration check (<environment>)`）：任何一套的資料庫比要部署的版本新，**整組都不部署**，
   主機什麼都不動（見〈[回滾與 migration](#回滾與-migration)〉）。
4. 建兩份 production image 推到 GHCR：`ghcr.io/<帳號>/<repo>-api:<組名>` 與 `-web:<組名>`（全小寫）。
   只建一次，這次部署的每一組各標一個組名。image 只標組名，執行中的版本看 `APP_VERSION`
   （設定頁顯示的就是它）；不同組用不同標籤，先行測試的組部署新版時不會蓋掉其他組的 image。
5. **一次一套**依序部署，每套是一個獨立的 job（`deploy (<environment>)`）：檢查 secrets →
   SSH 到主機 → `make backup allow-fresh`（資料庫與上傳檔案，期間 nginx 暫停；在 checkout 之前，
   備份檔才會標上線上那一版的版號）→ `git checkout` 同一個 tag（compose 檔與 nginx 模板是從原始碼
   bind mount 的）→ 拉 image 並重啟（`make start`）→ `make services` → 清掉被取代的舊 image →
   只留最近 `BACKUP_KEEP` 組備份。
   **一套失敗不會中斷其他套**。
6. 每套的結果看執行頁面左側的 **job 列表**（一套一行，失敗的標紅叉）。**Annotations** 會寫出
   停在主機上的哪一步（例如「備份失敗」、「啟動服務失敗」、「連不上主機」）。點進失敗的 job，
   失敗的步驟會自動展開 log；修好之後按 **Re-run failed jobs**，只會重跑失敗的那幾套。
7. 部署完清理 GHCR（`cleanup-ghcr`）：每次 push 都把組名標籤移到新的 image，舊的變成沒有標籤的版本，
   回滾又是從 tag 重建，它們沒有用處。只刪**沒有標籤、也沒被有標籤的 index 引用**的版本，
   再確認 registry 上**所有標籤**（不只這次部署的組）的 image 都還完整，結果寫在 Summary。
   清理失敗只留警告（下次部署會一起清）；確認失敗這個 job 會變紅，線上照常在跑，
   但下次部署或 Re-run 會拉不到 image，重跑一次部署（重新 build）就會恢復。

**不要在 GHCR 網頁上把 untagged 全選刪掉**：image 帶 attestation 時，標籤指向的是一份目錄（index），
真正的 image 和 attestation 在列表上也顯示成 untagged，刪掉之後那個標籤就拉不到了。
要手動清就對最近一個 tag 按 Run workflow，清理與確認會照上面的規則跑。

一次部署可能包含好幾組，所以**整個 repo 的部署共用一個排隊群組**，依序跑。
GitHub 同一個排隊群組最多「一個在跑、一個在等」，再排進第三個時，**原本在等的那個會被取消**。

部署前的備份依主機狀態處理：

| 主機狀態 | 處理 |
|---|---|
| 資料庫在跑 | 照常備份 |
| 連資料 volume 都沒有（全新主機） | 沒有東西可備份，略過，直接部署 |
| 有資料 volume，但資料庫沒在跑 | 主機狀態不是預期的，**中止**，先上主機看過 |
| 沒有 uploads volume（還沒部署過有它的版本） | 只備份資料庫 |

服務起來之後才清舊備份，只留最近 `BACKUP_KEEP` 組（見〈[備份與還原](#備份與還原)〉）。
**清理失敗不會讓部署變紅**，執行頁面只留一個警告，上主機手動 `make backup prune <組數>` 即可。

清舊 image 只清這個 repo 的（以 `org.opencontainers.image.source` 標籤辨認）、已經沒有容器在用的，
不碰主機上其他專案的 image，**也從不碰 volume**。同一台主機上其他套系統還在用的舊 image 不算沒人用，
輪到它們更新之後才會被清掉。

主機上 shell 有 `API_IMAGE` 與 `WEB_IMAGE` 時，`make start` 改成拉 image、不在主機上建置；
兩個都沒有就在本機建置，所以手動 `make start` 照常可用（一樣要停在發版的 tag 上）。

**首次設定**：主機上**不必**先把服務跑起來，也不在主機上建置 image。照上一節的指令做到
`docker` 群組與 `make init prod` 就停（**不要跑 `make start`**），其餘交給第一次發布：

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
- [ ] 第一次推上去之後，到 GHCR 的 package 設定確認 Visibility：image 裡有完整的程式碼（但沒有機密），
      **私有 repo 要設 Private**；公開 repo 的 image 內容等於原始碼，設 Public 也可以，而且免費。
      **改成 Public 之後就改不回 Private**
- [ ] 同一個時候確認 `-api` 與 `-web` 兩個 package 的 **Manage Actions access** 有這個 repo，
      角色是 **Admin**：`cleanup-ghcr` 要刪除舊版本。權限不夠時清理只留警告，舊版本會一直累積
- [ ] 要改每套保留的備份組數時，在 Variables 加 `BACKUP_KEEP`（正整數，沒設就是 10）；
      放在 repo 層級是所有系統的預設，個別 environment 也設的話以那份為準。設成不是正整數的值，
      那套系統在連上主機之前就會失敗
- [ ] repo 的 Settings → Variables 加 `PUBLISH_TARGETS`（例如 `production`）；要用 pre-release
      先行測試時再加 `PRE_RELEASE_TARGETS`（例如 `canary`）
- [ ] 想要「發布之後再核准一次」：在 environment 開 Required reviewers
      （每個 environment 各自核准，一組有三套就要核准三次）

第一次部署完成後，在主機上用 `make db superuser` 建立超級管理者（見〈[建立超級管理者](#建立超級管理者)〉）。
這是系統初始化的一環，部署流程刻意不代建。

主機以前手動 `make start` 建過 image 的話，那些 image 與建置快取 CD 用不到，
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

1. 主機上 clone 到新的目錄，例如 `/srv/system-b`，`make init prod`。`.env` 的
   `COMPOSE_PROJECT_NAME`、`SYSTEM_PORT` **不可以與同主機的其他套重複**（容器、volume、
   network 都以前者為前綴）。專案名稱的預設值是目錄名稱，目錄取 `system-b` 時直接按 Enter，
   容器名稱就與目錄對得起來。
2. GitHub 建 environment，例如 `production-system-b`，照〈首次設定〉填 secrets，並加上同樣兩條
   部署規則（tag `v*`、branch `main`）；`DEPLOY_PATH` 指向新目錄，同主機的其他 secrets 與其他套相同。
3. 確認它的組列在 `PUBLISH_TARGETS` 或 `PRE_RELEASE_TARGETS`（是新的組才需要加）；下一次發布
   （或對目前的 tag 按 Run workflow）就會部署到它。
4. 同主機有多套時，HTTPS 與網域由主機上的 reverse proxy 依網域轉到各套的 `SYSTEM_PORT`。
   網域還沒決定時先用 SSH tunnel 檢查，決定後照〈[設定網域](#設定網域)〉做（見〈[主機的 reverse proxy](#主機的-reverse-proxy)〉）。

#### 停用一套系統

在主機上停掉（`make services down`，資料留在 volume）之後，下一次部署到這一組時，**這套會在備份那一步中止**
（有資料 volume 但資料庫沒在跑），不會被自動重新啟動，其他套照常更新，只是這次部署會標成失敗。
要長期停用就刪掉或改名它的 environment（改成不屬於任何部署組的名稱），它就不會再被納入。

停用期間，它的舊 image 可能在其他套更新之後被清掉；資料不受影響。重新啟用時對目前的 tag 按一次
Run workflow 就會拉回來。

**發版**：先盤點相依落後多少、要不要整批升級（見 [`development.md`](development.md#相依升級)），
再 `make release <版號>` → 看過 diff 後 commit、push → 在 GitHub 建 release，tag 填 `v<版號>`，按 Publish
（要先行測試就勾 pre-release，見上方〈自動部署〉）。

`make release` 改檔之前會先檢查，任何一項不過就停、什麼都不改（`scripts/lib/release.sh`）：
版號是 `X.Y.Z` 且不帶前導零、比目前的 `APP_VERSION` 大（逐段比數字）、CHANGELOG 還沒有這個版號、
`[Unreleased]` 不是空的、工作目錄乾淨、在 `main` 且與 `origin/main` 一致、tag `v<版號>` 不存在、
契約與程式碼一致。契約不一致時不會在這裡重產：那代表 `main` 上有繞過 CI 的東西，先走 PR 修好。

還沒發過版的專案 `APP_VERSION` 是 `0.0.0`，CHANGELOG 的 `[0.0.0]` 是專案初始化的基準點（沒有對應的
tag），第一版是 `make release 0.0.1`。

跟 git tag 對齊的版號只有兩處：後端的 `APP_VERSION` 與 CHANGELOG 的版本段落；只改了 api 或 web
也一樣升這一個。前端顯示的版號經 `GET /api/system/version` 取自 `APP_VERSION`。
`make release` 會改 `APP_VERSION`，並把 CHANGELOG 的 `[Unreleased]` 改成這個版號；不要手動改，
`make check` 會擋下兩者不一致（`apps/api/tests/test_version.py`）。

其餘的版號**刻意不跟發版**，有實際變更時才改，git 上的 diff 才代表真的有東西變了：

| 版號 | 什麼時候改 |
|---|---|
| `pyproject.toml`、`uv.lock`、`package.json`、`package-lock.json` 的專案版號 | 那個套件本身有變更時才改，不跟發版 |
| OpenAPI 的 `info.version` | 固定是 `"1"`，不改（[說明](architecture.md#前後端契約)）；契約的變更看 `contracts/openapi.json` 的 diff |

**部署到其他組，或重新部署某個版本（回滾）**：Actions → Deploy → **Run workflow**，branch 選 `main`，
填一個已經存在的 tag（例如上一版的 `v0.1.0`）與 `target`（要部署的組，多組用空格分開）。
它走同一套流程（版號檢查、CI、從那個 tag 重建這一組的 image、逐套備份與部署），只是不建新的 tag；
發新版仍然要走發布 release。回滾一樣是**整組一起**。GHCR 不保留舊版 image，回滾一律從 tag 重建，
重建出來的 image 與當初不會逐 byte 相同（相依由 lock 檔固定，差異在 base image 的系統層）。
也可以用指令觸發：

```bash
gh workflow run deploy.yml --ref main -f tag=v0.1.0 -f target="production staging"
```

#### 回滾與 migration

**migration 只往前，回滾只換程式。** 要部署的版本和線上版本的 migration 一樣時，回滾照常；
兩版之間多了 migration（資料庫比要部署的版本新）時，部署前的檢查會拒絕，整組都不動。
這時有兩條路：

- **往前修**（建議）：修好之後發一個新版本。
- **還原部署前的備份**（會失去備份之後的資料）：在主機上 `git checkout v<舊版號>`，`make db restore`
  選那一版留下的備份（資料庫連同 migration 的版本一起退回），再 `make start`。

`make db restore` 只列出與 checkout 版本一致的備份，部署前的備份標的是當時線上的版本 ——
**前提是它還沒被清掉**：部署後只留最近 `BACKUP_KEEP` 組，不分版號，之後又部署過很多次的話，
那一版的備份可能已經不在了。真的需要長期保留某一版，自己把那組備份搬出 `backups/`。

在主機上手動 `git checkout` 舊版再 `make start` 也一樣：單獨跑的 migrate 會失敗而不切換服務，
這時 checkout 回原本的 tag 即可。

### 可觀測性只到 stdout

- **有**：後端寫到 stdout 的請求紀錄（方法、路徑、狀態碼、耗時，**不含 query string**），以及
  web、api、postgres 的 Docker healthcheck。
- **有** request id：每行紀錄開頭的 `[xxxxxxxx]` 由 nginx 產生，經 Next 傳到後端並回寫到回應標頭，
  同一次操作在三個服務的 log 裡是同一個 id。
- **看 log** 用 `make services logs [服務]`。正式環境每個容器只留 10MB × 5 份（prod overlay），
  **重建容器時舊的 log 會一起消失**，要長期保存就自己轉送到別處。
- **沒有**：結構化 log、錯誤追蹤（Sentry 之類）、指標與告警。模板刻意不內建：做法依部署平台而定，
  而且錯誤內容可能帶著使用者資料，送不送到第三方要由專案決定。所以出錯時不會有人收到通知，
  要等使用者回報再上主機查（[ADR 0008](decisions/0008-no-built-in-error-tracking.md)）。
- **最大的盲點是瀏覽器端的錯誤**：前端 JavaScript 在使用者的瀏覽器裡出錯時（按了沒反應、畫面白掉），
  主機上的 log 一行都沒有。需要時先補錯誤追蹤（Sentry，或自架、與它相容的 GlitchTip），
  DSN 走執行期設定（後端 `app/config.py`、前端 `shared/runtime/`）。

## 帳號

帳號、角色、Session 怎麼運作見 [`features/`](features/README.md)。這裡只放要在主機上執行的操作。

### 建立超級管理者

```bash
make db superuser
```

互動式輸入暱稱、帳號、密碼（密碼不回顯），可以重複執行。第一個超管、再加一個超管，
以及唯一的超管失聯時的救援，都用這個指令（理由見 [帳號、角色與密碼](features/accounts-roles.md#帳號)）。

### 套用 `.env` 的變更

`.env` 改了要重建容器才會生效（`make services restart` 不會套用）。接了 CD 的主機**不要直接
`make start`**：主機的 shell 沒有 `API_IMAGE`／`WEB_IMAGE`，它會改成在主機上建置 image。改用重新部署：

1. 在主機上改好 `.env`。
2. Actions → Deploy → **Run workflow**，branch 選 `main`，`tag` 填目前線上的版本（`make services`
   上方顯示的），`target` 填這台主機所在的組。主機會拉 image、以新的 `.env` 重建容器，不在主機上建置。

- 這是**整組**重新部署：同一組的其他系統也會跑一次備份與部署，它們的設定沒變，影響只有備份時
  nginx 暫停的那幾秒。
- 改完 `.env` 到部署完成之間，線上跑的仍是舊值，兩步接著做。
- 沒接 CD 的主機只能 `make start`（會在主機上建置；原始碼沒變的話大部分步驟會用到快取）。

### 讓所有人登出

```bash
make db revoke-sessions
```

確認後所有使用者的 token 立刻失效（包含執行的人自己），不用改 `.env`、不用重新部署。用在帳號被盜、
懷疑 token 外流的時候；之後所有人同時重新登入的負擔見 [Session](features/session.md#撤銷)。

### 更換 `JWT_SECRET_KEY`

金鑰外洩時要換掉金鑰本身，`make db revoke-sessions` 擋不住（理由見 [Session](features/session.md#撤銷)）。
在主機上產生新值換掉 `.env` 的 `JWT_SECRET_KEY`（產法與 `make init` 相同），再照
〈[套用 `.env` 的變更](#套用-env-的變更)〉重新部署。舊金鑰簽的 token 會全部失效，所有人都要重新登入。

```bash
openssl rand -hex 32
```

## 主機的 reverse proxy

compose 裡的 nginx **一定在主機的 reverse proxy 後面**：HTTPS、網域、同主機多套系統的分流都由主機那層處理，
範例在 [`infra/host-nginx/example.conf`](../infra/host-nginx/example.conf)。兩層的分工：

| | 主機的 nginx | 容器內的 nginx |
|---|---|---|
| 面對誰 | 用戶端 | 只有主機（port 綁 `127.0.0.1`） |
| `X-Real-IP` | 以 `$remote_addr` **覆寫** | 信任私有網段送來的值，換成用戶端 IP |
| `X-Forwarded-Proto` | 以 `$scheme` 送出（`https`） | 沿用 `http`／`https`，沒送時用自己的協定 |
| 上傳上限 | 16m（與專案固定的上限相同） | 16m（與 Next 相同） |
| HSTS、HTTP/2 | 由這層處理（TLS 在這裡結束） | 不處理 |
| 版本號 | `server_tokens off` | `server_tokens off` |

主機那層少了任何一項都**不會有錯誤訊息**：

- 沒送 `X-Real-IP` → 後端看到的是主機的位址，所有使用者共用同一個登入限流額度，一個人打爆全站被鎖。
- 沒送 `X-Forwarded-Proto` → cookie 不帶 `Secure`（`shared/session/cookie-options.ts`）。
- `client_max_body_size` 沒設 → nginx 預設 1m，超過的上傳在主機就被擋下。

**容器 nginx 信任上一層的前提是外部連不到它**。compose 把 port 綁在 `127.0.0.1`，只有主機上的程式連得到；
改回 `0.0.0.0` 的話，任何人都能直接連進來、自己帶 `X-Real-IP` 冒充別人的 IP。Docker 直接改 iptables，
**主機的 ufw 擋不住它開的 port**，所以不能靠防火牆補。`apps/api/tests/test_nginx_trusted_proxy.py` 守住這幾件事。
開發機的 `make start lan` 會改綁 `0.0.0.0`（寫在 dev overlay），prod overlay 不碰 port，`MODE=production` 時也會拒絕。

LB 在**另一台機器**時，它連不到 `127.0.0.1`：要改 compose 的綁定位址，並且用防火牆或安全群組確保只有
LB 連得到，再把 `infra/nginx/snippets/trusted-proxy.conf` 的 `set_real_ip_from` 縮到 LB 的網段。

### 還沒有網域時：用 SSH tunnel 檢查

部署後想確認系統正常，但子網域還沒決定時，**不要為了測試開放 port 或在主機 nginx 開一個用 IP 連的站**。
用 SSH tunnel 把主機上的 port 接到自己的電腦，主機什麼都不用改：

```bash
ssh -N -L 8080:127.0.0.1:<SYSTEM_PORT> <使用者>@<主機 IP>
```

連線保持開著，瀏覽器開 `http://localhost:8080`，關掉 SSH（`Ctrl+C`）就結束。本機的 `8080` 換成任何沒在用的 port 都可以，
避開本機開發的 `SYSTEM_PORT` 就好。

- 流量經過 SSH 加密，對外什麼都沒有開放。
- 沒有經過主機的 nginx，所以沒有 `X-Forwarded-Proto`：cookie 不帶 `Secure`，用 HTTP 也能正常登入。
- 容器看到的來源都是主機自己，所有人共用一份登入限流額度；只有自己測試時沒有影響。

### 設定網域

**憑證要先申請，才能套用 [`example.conf`](../infra/host-nginx/example.conf)**：它引用的憑證檔還不存在時，
`nginx -t` 會失敗，無法 reload。

1. DNS 加一筆 A 記錄，把子網域指到主機 IP。`dig +short <子網域>` 回傳主機 IP 才算生效。
2. 主機 nginx 先放**只有 HTTP** 的設定，讓 certbot 可以驗證網域：

   ```nginx
   server {
       listen 80;
       server_name <子網域>;
       client_max_body_size 16m;

       location / {
           proxy_pass http://127.0.0.1:<SYSTEM_PORT>;
           proxy_set_header Host              $host;
           proxy_set_header X-Real-IP         $remote_addr;
           proxy_set_header X-Forwarded-Proto $scheme;
       }
   }
   ```

   `sudo nginx -t && sudo systemctl reload nginx`。
3. `sudo certbot --nginx -d <子網域>`：certbot 會加上 `listen 443 ssl`、憑證路徑，以及 HTTP 轉 HTTPS。
4. 照 `example.conf` 在 443 的區塊補上 `server_tokens off`、HSTS，`listen 443 ssl` 改成 `listen 443 ssl http2`，
   再 reload 一次。標了 `managed by Certbot` 的行保留原樣，certbot 續約時會找這些標記。

套用設定一律用 `reload`，不要用 `restart`：reload 不會中斷現有連線，新設定有錯時也會保留舊的繼續運作。

完成後確認：

- `curl -sI https://<子網域> | grep -iE "^HTTP|^server|strict-transport"`：回應是 `HTTP/2`、`server` 不帶版本號、有 HSTS。
- 主機上 `sudo ss -ltnp | grep <SYSTEM_PORT>` 顯示 `127.0.0.1:<SYSTEM_PORT>`，外部連 `http://<主機 IP>:<SYSTEM_PORT>` 連不上。
- 登入後在瀏覽器確認 cookie 帶 `Secure`。

## 用戶端 IP 與限流

登入與改密碼的限流（規則見 [限流](features/rate-limit.md)）以用戶端 IP 計數。
後端只讀 `X-Real-IP`：容器 nginx 先依主機送來的值換掉 `$remote_addr`（見上一節），再以它覆寫這個標頭，
`apps/api/tests/test_nginx_templates.py` 確保每個 location 都有覆寫。

### 單一行程，不能直接加副本

API 是**單一 Python 行程**（沒有 workers，compose 也沒有 replica）。限流的計數存在行程記憶體裡，
加 workers 或副本會讓允許次數直接變成 N 倍，而且沒有任何症狀。要水平擴充時，**先**把
`RateLimiter` 的計數換成 PostgreSQL，**再**加副本（不用 Redis 的理由見 [ADR 0005](decisions/0005-in-process-rate-limit.md)）。

初始資料（seed）由 migrate 服務寫入，api 開機時不寫任何東西，所以加副本不受它影響。

## 備份與還原

`make backup` 是唯一的備份入口，資料庫與上傳檔案一起備份，兩份共用同一個檔名，只差副檔名；
還原則分開：

```bash
make backup                          # backups/<專案>_v<版號>_<日期>_<時間>.dump 與 .tar
make db restore                      # 列出這個目錄版本的資料庫備份，選一個並確認後還原
make db restore backups/x.dump       # 直接指定檔案（版本必須與 make services 上方的版本一致）
make uploads restore                 # 列出所有上傳檔案的備份，選一個並確認後還原
make uploads restore backups/x.tar   # 直接指定檔案
```

沒有只備份一邊的指令：單邊的備份配不成一組，還原時容易選錯。

**備份期間對外服務會暫停**：先停 nginx（唯一的對外入口，用 `stop` 不是 `down`），備份完、或備份
失敗時都會重新啟動。沒有新的寫入，資料庫與上傳檔案才是同一個時間點；api 與 web 不停，因為上傳
檔案是從 api 容器裡打包的。

**還原前會先完整備份一次**（等於自動跑一次 `make backup`），選錯檔案時還退得回來；這次備份失敗
就不還原。整段在 nginx 停著的時候做，還原到一半時不會有請求讀寫到新舊混雜的資料。

**資料庫**用 `pg_dump`，清單只列出與這個目錄版本一致的備份，新到舊，例如 `1) v0.0.2 2026-10-17 08:35:53`。
**還原只接受目前版本的備份**：別版的資料表結構可能跟目前的程式對不上，要還原別版的備份就先部署回那一版。
檔名沒有版號的舊備份不會列出，真的要用時自己改名成上面的格式。
還原會**取代備份裡有的資料表**（`pg_restore --clean`）；備份之後才新建的表不會被刪掉。

**上傳檔案**是 uploads volume（api 的 `/app/uploads`）整包打成 `.tar`，不壓縮（圖片、影片本身已經壓過）。
檔案沒有結構，**任何版本的備份都能還原**。還原會先清空 volume 再解開，備份之後才上傳的檔案會消失。
兩邊分開還原時，自己確認選的是同一組（同樣的日期與時間），否則資料庫裡的紀錄可能指到不存在的檔案。

**清理**以組為單位、依檔名的時間、不分版號，只刪符合上面命名的檔案。部署時會自動清
（`BACKUP_KEEP`，見〈[自動部署](#自動部署)〉），手動 `make backup` 不會。

### 內部指令

部署與腳本自己用的指令，不列在 `make help`：

```bash
make backup allow-fresh              # 同 make backup，但全新主機（還沒有資料 volume）時略過（部署用）
make backup prune 10                 # 只留最近 10 組，同名的 .dump 與 .tar 一起刪（部署後自動跑）
make version                         # 這個目錄的版本（APP_VERSION），例如 v0.0.2
make db revision                     # 資料庫目前的 migration revision，全新主機什麼都不印（部署前的檢查用）
```

`backups/` 只在這台機器上，**正式環境要自己安排排程與異地保存**，並定期實際還原一次 ——
沒有演練過的備份等於沒有備份。上傳檔案通常比資料庫大得多，留意主機的磁碟空間。
