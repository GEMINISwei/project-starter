# 部署與維運

生產部署、帳號初始化與運行期的安全設定。本機開發環境見
[`development.md`](development.md)。

## 生產部署

**兩條路，選一條。** 差別只在「image 從哪來」，啟動順序、overlay 與運行期設定完全相同。

```bash
make prod      # 在這台主機上就地建置 image 再啟動
make deploy    # 拉 registry 上已建好的 image 再啟動（需要先接上 CI/CD）
```

`make deploy` 部署的是 `.env` 裡 `IMAGE_TAG` 指定的那一版；CD 不走這條，它直接呼叫
`bash scripts/deploy.sh <tag>` 把要部署的 tag 當參數帶進去，不受主機 `.env` 影響。

模板出廠預設是 `make prod` —— clone 完、`make init` 完就能用，不必先有 registry。
接上 CI/CD 之後改用 `make deploy`，理由與設定見下面的
[registry 模式](#registry-模式build-once-deploy-anywhere)。

`docker-compose.yml` 是兩種模式共用的底稿，**dev 與 prod 各自再疊一份 overlay**
（`.dev.yml`／`.prod.yml`），沒有哪一邊是「預設值」。前端以 Next.js standalone 模式
建置（image 較小）。

prod 的 overlay 多兩樣東西。一是 `x-prod-runtime` 的 **logging 上限**（json-file driver
預設無上限，長跑的部署會把磁碟寫滿）；dev 刻意不設，因為 dev 的容器活不久，
轉檔只會讓 `make logs` 翻不到早一點的訊息。**`restart: always` 不在 overlay 裡** ——
它在共用底稿，dev 與 prod 都有。

二是**記憶體上限**：api 與 web 各 512M、postgres 1G。`migrate` 刻意不設上限，
理由寫在 `docker-compose.prod.yml` 的同一段 —— 一次性的資料轉換用多少記憶體取決於
資料量，設一個猜出來的數字只會讓大 migration 被 OOM kill，而那是最不該失敗的時機。
**部署後發現 api 週期性重啟時，這裡是第一個要看的地方。**
旗標組合由 `scripts/lib/compose.sh` 統一產生，不要自己拼。

啟動順序由 compose 的 healthcheck 與 `depends_on` 決定：

```text
postgres → migrate → api → web → nginx
```

`migrate` 是一次性容器，跑完 `scripts/db.py migrate` 就退出；api 以
`depends_on: migrate: service_completed_successfully` 等它**成功結束**才啟動。
任何一支 migration 失敗，整個部署就停在那裡，不會有任何服務對外開放 ——
**「新版程式碼配上舊資料結構」這個狀態在機制上不可能出現。**

部署前的檢查清單：

- 以 reverse proxy 或雲端 load balancer 提供 HTTPS；應用程式不直接負責 TLS termination。
  **若在 nginx 前面再加一層 proxy（CDN、ALB、公司內的反向代理），必須一併調整取用戶端 IP
  的方式** —— 見下方「用戶端 IP 與限流」。
- 將對外流量限制至 web，PostgreSQL 與 api 僅允許內部網路存取。
- 將 `.env` 的預設密碼與 `REGISTER_KEY` 全部替換，並妥善保管 `JWT_SECRET_KEY`。
- 建立定期備份、異地保存與實際還原演練；`make backup` 產物位於主機 `./backups/`。
- 依部署平台設定服務監控；web、api 與 PostgreSQL 均已提供 Docker healthcheck。

### 準備部署主機

**兩條路都要做這一節**，`make prod` 與 `make deploy` 的差別只在第 4 步。指令在**主機上**跑。

```bash
# 1. 把 repo 放到你打算長期擺它的絕對路徑。這個路徑之後會是 CD 的 DEPLOY_PATH。
#    remote 名稱**必須是 origin** —— deploy.yml 進來之後跑的是 `git fetch ... origin`。
sudo mkdir -p /srv/<專案名> && sudo chown "$USER" /srv/<專案名>
git clone <你的 repo> /srv/<專案名>
cd /srv/<專案名>

# 2. 產 .env。主機上的祕密要自己一份，不要從開發機抄。
#    prod 的 compose 對大部分變數是 `${VAR:?}`，少一個就起不來。
make init

# 3. 這個帳號要能不透過 sudo 跑 docker，做完要**重新登入**才生效。
sudo usermod -aG docker "$USER"

# 4. 只有 registry 模式要做：填 IMAGE_REGISTRY，並登入 GHCR。
#    走 make prod 的話跳過這一步，IMAGE_REGISTRY 留空就是就地建置。
#    **前綴一律小寫**（見下面「IMAGE_REGISTRY 必須全小寫」）。
sed -i 's|^IMAGE_REGISTRY=.*|IMAGE_REGISTRY=ghcr.io/<owner>/<repo>|' .env
docker login ghcr.io -u <你的帳號>    # package 設成 public 可略過

# 5. 起起來看看。走 registry 模式的話這裡還沒有 image 可拉，先用 make prod 確認主機本身沒問題。
make prod
```

打開 `http://<host>:<SYSTEM_PORT>`，照「首次初始化」建立第一個超級管理者。

**主機上留著這份原始碼不是裝飾。** compose 檔與 nginx 模板是 bind mount 進容器的，
只有 api／web 兩個 image 會來自 registry。CD 因此會把這個工作樹 `git checkout --detach`
到要部署的 commit，再拉 image —— 原始碼與 image 一起換，不會出現「舊 image 配新設定」。
`.env` 不受影響，它在 `.gitignore` 裡。

走 `make prod` 的到此為止。要接 CD 的往下走。

### registry 模式：build once, deploy anywhere

`make prod` 每次部署都在主機上重建 image。那表示**上線的東西跟 CI 驗過的不是同一份**，
主機要裝建置工具鏈，而且沒有可回滾的單位 —— 要退版只能 `git checkout` 舊 commit 再重建，
而重建出來的東西不保證跟當初上線的一樣。

registry 模式把建置移到 CI：`.github/workflows/ci.yml` 的 `publish` job 在所有檢查
綠燈之後，把 `ghcr.io/<owner>/<repo>/api` 與 `/web` 推上 GHCR；主機只負責 pull。
回滾因此變成「換一個 tag 再跑一次」，不必重建也不必重跑 CI。

#### 一次性設定

**只有走 registry 模式才要做這一節。** `make prod`（主機就地建置，`make init` 的出廠預設）
不需要在 GitHub 設定任何東西 —— 那條路連 `.github/` 都可以整個刪掉。

| 在哪 | 設什麼 | 必要嗎 |
|---|---|---|
| 主機 `.env` | `IMAGE_REGISTRY=ghcr.io/<owner>/<repo>`（**全小寫**，見下）；`IMAGE_TAG` 走 CD 就留空（tag 由 workflow 當參數帶），只有要在主機手動 `make deploy` 才填 | 必要 |
| 主機 | `docker login ghcr.io`（唯讀 PAT） | package 設成 public 可略過 |
| 主機 | 能免互動 `git fetch` 這個 repo 的憑證（見下） | 必要 |
| GitHub → Environments | 建一個叫 `production` 的。**不必設 required reviewers** —— 核可靠手動觸發，見下面的「發版與回滾」（public repo 想加是免費的，算加強不算必要） | 必要 |
| environment secret | `DEPLOY_SSH_KEY`、`DEPLOY_SSH_KNOWN_HOSTS` | 必要 |
| environment variable | `DEPLOY_HOST`、`DEPLOY_USER`、`DEPLOY_PATH`（**絕對路徑**，見下） | 必要 |
| repository variable | `UPLOAD_SIZE_LIMIT` | 選用，預設 `1mb` |

`DEPLOY_*` 那幾個放 environment 層。**這裡沒有任何 repository 層的 secret** ——
`NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` 曾經要放在這裡，現在它是純粹的執行期值，只存在於
主機的 `.env`（理由見 [`../apps/web/Dockerfile`](../apps/web/Dockerfile) 的長註解）。

##### 照著跑

**前置：** 上面的「準備部署主機」要先走完（repo 在 `DEPLOY_PATH`、`.env` 有了、
`IMAGE_REGISTRY` 填了、`docker login` 過了、那個帳號進得了 docker 群組），
再加上下面「主機要能免互動地 `git fetch` 這個 repo」那一段的 deploy key。
第 4 步的預檢就是在驗這些 —— 沒先做的話它會一次噴四個錯。

`<host>`／`<user>`／`<專案名>` 換成你的。`gh` 要先 `gh auth login`，指令都在**你自己的機器上**跑。

```bash
# 0. 建 environment。底下的 `gh secret set --env production` 需要它先存在，
#    environment 不存在時那幾行會直接失敗。
gh api --method PUT "repos/{owner}/{repo}/environments/production"

# 1. 產一把只給 CD 用的金鑰。不要沿用你的個人金鑰 —— 這一把會放進 GitHub。
ssh-keygen -t ed25519 -C "deploy@<專案名>" -f ./deploy_key -N ""

# 2. 公鑰裝到部署主機那個帳號上，然後確認免密碼進得去
ssh-copy-id -i ./deploy_key.pub <user>@<host>
ssh -i ./deploy_key -o BatchMode=yes <user>@<host> true && echo OK

# 3. 主機的公開金鑰指紋。deploy.yml 用它而不是 StrictHostKeyChecking=no ——
#    後者等於接受任何冒充成部署主機的東西。
ssh-keyscan -H <host> > ./known_hosts

# 4. **寫進 GitHub 之前先預檢。** 用剛產的金鑰把 CD 會走的每一段真的走一次：
#    進得去、跑得動 docker、cd 得到、fetch 得到。任何一項不成立就先修，不要先寫值 ——
#    值寫進去之後，錯誤要到部署跑到一半才顯現（見下面 DEPLOY_PATH 那條）。
ssh -i ./deploy_key -o BatchMode=yes <user>@<host> \
  "echo SSH_OK && docker ps -q >/dev/null && echo DOCKER_OK \
   && cd '<DEPLOY_PATH>' && grep -q '^IMAGE_REGISTRY=ghcr' .env && echo ENV_OK \
   && git fetch --tags --prune origin && echo FETCH_OK \
   && docker pull ghcr.io/<owner>/<repo>/api:main && echo PULL_OK"

# 5. 寫進 GitHub。私鑰與 known_hosts 走 environment 層。
gh secret set DEPLOY_SSH_KEY         --env production < ./deploy_key
gh secret set DEPLOY_SSH_KNOWN_HOSTS --env production < ./known_hosts
gh variable set DEPLOY_HOST --env production --body "<host>"
gh variable set DEPLOY_USER --env production --body "<user>"
gh variable set DEPLOY_PATH --env production --body "/srv/<專案名>"

# 6. 選用：build 期的上傳上限。**要與主機 .env 的值相同**，不一致的話 web 會在啟動時
#    自己結束行程（理由見下面的「唯一的 build 期值」）。不設就是預設的 1mb。
gh variable set UPLOAD_SIZE_LIMIT --body "1mb"

# 8. 私鑰用完就刪，它已經在 GitHub 與主機兩邊了
rm -f ./deploy_key ./deploy_key.pub ./known_hosts
```

設完確認一次：

```bash
gh secret list;   gh secret list --env production
gh variable list; gh variable list --env production
```

真正的驗證是**跑一次**：Actions → Deploy → Run workflow，`ref` 填 `main`。

**先確認 `main` 上有一次綠燈的 CI。** 部署的第二步會等那個 commit 的 CI 結論
（見下面的「Deploy workflow 做了什麼」）—— 沒有的話第一次部署會停在等 CI 那一步。

CI 綠燈之後，「讀出目前線上的版本」那一步會先單獨探一次 SSH，連不上就直接中止 ——
所以金鑰或 known_hosts 設錯會在動到線上任何東西**之前**就停下來。但它排在等 CI 之後，
所以設錯的時候可能要先等 CI 那一步跑完，才會看到 SSH 的錯誤。

**`DEPLOY_PATH` 要用絕對路徑。** `deploy.yml` ssh 進去之後直接 `cd '$DEPLOY_PATH'`，
而非互動 session 的起點是 `DEPLOY_USER` 的家目錄 —— 填相對路徑時它的意義取決於「誰登入」，
那是部署設定裡最不該用猜的一件事。

填錯的壞法特別難追：先跑的「讀出目前線上的版本」是 `cat '$DEPLOY_PATH/.deployed'`，
路徑錯只是讀不到檔案，跟「全新主機第一次部署」**長得一模一樣**，於是它印一句 warning 就放行；
真正的失敗要到後面 `cd` 那步才發生，而那時回滾安全網已經因為那句 warning 而關掉了。
上面第 4 步的預檢就是為了讓這件事在寫入 GitHub 之前就爆出來。

**`DEPLOY_USER` 要能不透過 `sudo` 執行 docker**（`usermod -aG docker <user>` 之後重新登入）。
CD 不會幫你 `sudo`，少了這個權限的症狀是部署那步失敗，而錯誤訊息講的是 docker socket 權限，
不會指回這裡。

用 `root` 當 `DEPLOY_USER` 可以，代價要知道：**任何能觸發 Deploy workflow 的人，就等於能拿到
那台主機的 root**。想收斂就另開一個只屬於這個專案的帳號（加進 docker 群組、給它 `DEPLOY_PATH`
的擁有權），金鑰外洩的上限就從整台機器縮到這一個專案。注意那時主機那把讀 GitHub 的金鑰與
`~/.ssh/config` 也要搬到新帳號的家目錄。

**主機的 SSH 必須在 22 port。** `deploy.yml` 的 `ssh` 沒有帶 `-p`，換 port 的話那幾行
與 `ssh-keyscan` 都要自己加。

部署憑證只放在 GitHub 的 environment secret，**不要**放進主機或 repo 的檔案裡；
GHCR 的讀取憑證則相反，只放在主機的 `~/.docker/config.json`，不要進 CI。

**`IMAGE_REGISTRY` 必須全小寫。** `publish` job 推的是 `ghcr.io/${{ github.repository }}`，
而 `docker/metadata-action` 會自動轉小寫；`scripts/deploy.sh` 那一側是純字串串接、
不做任何 normalize。owner 或 repo 名含大寫時照字面抄進 `.env`，會得到
`invalid reference format: repository name must be lowercase` —— 而那句話不會告訴你
要去 `.env` 改大小寫。

**主機要能免互動地 `git fetch` 這個 repo。** repo 是 public 的話 HTTPS remote 匿名就
fetch 得到，這一段整段跳過。**private repo** 才需要一份**獨立於部署 SSH 金鑰**的讀取憑證：
在 repo 的 Settings → Deploy keys 加一把唯讀公鑰（不勾 write），主機用 SSH remote。
底下四件事各自對應一種「設定當下看起來沒事、CD 跑到一半才失敗」的錯法。

**不要拿帳號層的 SSH key 充數**（Settings → SSH and GPG keys），即使主機上已經有一把在用。
那一把代表**你這個人**，能讀寫你有權限的每一個 repo；deploy key 只綁一個 repo，
不勾 write 就是唯讀。主機被入侵時，兩者的差別是「整個帳號的推送權」與「一個 repo 的讀取權」。

**這把金鑰不能有 passphrase**（`ssh-keygen -N ""`）。CD 的 `git fetch` 跑在沒有人在鍵盤前面的
session 裡，有 passphrase 的金鑰在那裡不會被跳過，而是直接失敗。也不要改用 ssh-agent 補救 ——
agent 只活在互動 session 裡，CD ssh 進來的那個非互動 session 看不到它。
沒有 passphrase 在這裡是可以接受的，**因為權限範圍夠小**：那把金鑰能做的事上限是讀一個 repo。

**主機上已經有別把 `github.com` 的金鑰時，要用 Host 別名把兩者分開。** 否則 ssh 會把
`~/.ssh/` 底下的金鑰輪流試一遍，又試回那把有 passphrase 的，提示照樣跳出來：

```sshconfig
Host github-<專案名>
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_<專案名>_deploy
  IdentitiesOnly yes
```

remote 跟著改成 `git@github-<專案名>:<owner>/<repo>.git`。**`IdentitiesOnly yes` 不能省** ——
它就是「只試這一把」那句話，少了它別名等於沒設。

**驗證要走真正那條路**，不是 `ssh -T git@github.com`（有別名時它測的根本是另一把金鑰）：

```bash
GIT_SSH_COMMAND='ssh -o BatchMode=yes' git fetch --tags --prune origin
```

`BatchMode=yes` 禁止一切互動提示，所以這一跑的處境與結果，就是 CD 將來會遇到的那一個。
它問你任何東西或印出 permission denied，都代表 CD 會卡在那一步。

**金鑰與 `~/.ssh/config` 放在 `DEPLOY_USER` 的家目錄。** 換掉 `DEPLOY_USER` 時兩者都要跟著搬，
否則 CD 會在 `git fetch` 失敗，而訊息只說 permission denied，不會指回「家目錄找錯了」。

#### 發版與回滾

**發版是兩段，第二段是手動的。**

第一段是一個發版 PR，四樣一起改：

| 改什麼 | 內容 |
|---|---|
| [`../CHANGELOG.md`](../CHANGELOG.md) | `## [Unreleased]` 改名成 `## [1.2.3] - <日期>`，並在上面補一個新的空 `## [Unreleased]` |
| [`../apps/api/app/config.py`](../apps/api/app/config.py) | `APP_VERSION = "1.2.3"` |
| [`../contracts/openapi.json`](../contracts/openapi.json) | 跑 `make gen-types` 產生 —— `APP_VERSION` 是 OpenAPI 的 `info.version`，改了就是改契約（見 [`../AGENTS.md`](../AGENTS.md#改動後一定要做的事)） |
| `apps/web/shared/api/generated/schema.d.ts` | 同上，`make gen-types` 一起產出 |

合進 `main` 之後才打 tag：

```bash
git tag v1.2.3 && git push origin v1.2.3
```

tag push 會跑完整套 CI（含 `make check-version`：tag 必須是 `v$APP_VERSION`），
推出 `1.2.3`／`1.2`／`latest`／`sha-<short>` 四個 image tag。**到這裡為止還沒有任何東西上線。**
main 上的每次合併則推 `main` 與 `sha-<short>`。

> **`APP_VERSION` 是程式碼自述的版本，git tag 是發布過的標記。**
>
> `check-version` 只驗一個方向：打了 tag 就必須等於 `v$APP_VERSION`。它不要求每個
> `APP_VERSION` 都有對應的 tag —— 「有版號、沒有 tag」是允許的狀態，因為部署的身分是
> commit（見下面的「Deploy workflow 做了什麼」），`sha-<short>` 對每個 commit 都存在。
>
> 模板本身因此不帶 tag：`APP_VERSION` 是 OpenAPI 的 `info.version`，結構上不能是空的，
> 而模板沒有被部署過，沒有東西可以標記。下游保留 clone 下來的歷史，而 `git clone` 預設
> 會把 tag 一起帶走 —— 上游打的 tag 會出現在每個下游的 `git tag -l` 裡，標記著一個
> 他們沒有發布過的東西。下游的第一個 tag 打在自己第一次真的上線的那一版上。

第二段：**GitHub 的 Actions → Deploy → Run workflow，填要部署的 commit** ——
commit SHA、tag 或 branch 都可以（`abc1234`、`v1.2.3`、`main`）。等效的 CLI：

```bash
gh workflow run deploy.yml -f ref=v1.2.3
gh run watch    # 這一步會跑好幾分鐘，見下面的步驟說明
```

**那個手動動作就是核可閘門，這是刻意的。** 看起來更自然的做法是打 tag 自動部署，靠
environment 的 required reviewers 攔一道 —— 但 deployment protection rules 對 private repo
是付費功能，免費方案上那道閘門**根本不存在**，於是打一個 tag 就等於無人看管地直接動線上。
「有人到 Actions 頁面按下 Run workflow 並填入 commit」則不依賴任何方案，也沒有繞過的方法，
所以核可用它。

**repo 是 public 的話 required reviewers 是免費的**，值得加在 `production` environment 上 ——
它補的是手動觸發補不到的那一半：按的人與核可的人可以不是同一個。單人專案沒有差別，
所以這條 CD 仍然不預設它存在。

**回滾走同一條路**：Actions → Deploy → Run workflow，填要退回的那個 commit。

**但回滾退不了 migration。** 它退的是 image 與工作樹，資料結構留在新版 —— 所以
「這一版能不能回滾」是在**寫 migration 的時候**決定的，不是在按下 Run workflow 的時候。
規則與「改名、刪欄位要拆成兩次發版」的作法見
[`extending.md`](extending.md#資料庫-migration)，那一節是這個主題的 owner。

> **部署的身分是 commit，不是 image tag。**
>
> `deploy.yml` 把你填的 ref 解成 commit SHA，再由它推導 image tag（`sha-<前 7 碼>`）
> 與主機工作樹要對齊的位置 —— 方向為什麼是這樣，見該檔那一步的註解。
>
> 對操作的人來說只有三件事要知道：填 `v1.2.3` 與填那個 commit 的 SHA **結果完全相同**
> （同一份 digest）；`latest` 不是 git ref，填了會被擋下來；**原始碼會跟著 image 一起退**
> —— compose 檔與 nginx 模板是從主機工作樹 bind mount 的，只換 image 會讓
> 「舊 image 配新設定」上線。

要在主機上直接跑也可以，但那條路**不會**動到工作樹，只換 image：

```bash
bash scripts/deploy.sh sha-abc1234     # 設定沒動過的時候才夠用
```

#### Deploy workflow 做了什麼

六個步驟，前三步都還沒碰到線上。**知道順序是為了看懂錯在哪一步** —— 第 2 步失敗
與第 5 步失敗，該去修的地方完全不同。

| # | 步驟 | 失敗長什麼樣 |
|---|---|---|
| 1 | 把你填的 ref 解成 commit SHA，推導 image tag `sha-<前 7 碼>` | ref 在這個 repo 解不開（`latest` 這種浮動 image tag 不是 git ref，會停在這裡） |
| 2 | **等這個 commit 的 CI 結論**，最長 30 分鐘 | CI 紅／被取消／逾時就中止；等不到 run 也中止 |
| 3 | 把 `DEPLOY_SSH_KEY` 與 `DEPLOY_SSH_KNOWN_HOSTS` 寫成檔案 | 幾乎不會失敗 |
| 4 | 探一次 SSH，再讀主機的 `.deployed` 當回滾標的 | 連不上主機＝**錯誤**，當場中止；讀不到 `.deployed` 只留 warning 並繼續 |
| 5 | ssh 進主機 → `git fetch` → `checkout --detach` → `bash scripts/deploy.sh <tag>` | image 拉不到、compose 起不來、5 分鐘內沒 healthy、或健康了但外面連不到 |
| 6 | 第 5 步失敗時，用同一條路徑退回 `.deployed` 記的那一版 | 見下面「部署失敗會自動回滾」 |

第 2 步有兩件事會讓人卡住：

- **它只認 `push` 事件的 CI run。** `publish` job 帶 `if: push`，所以 PR 那次 run 是
  「綠燈但沒有推任何 image」。一個**只進過 PR、沒合進 `main` 也沒被 tag 的 commit
  部署不了** —— CI 看起來是成功的，image 卻不存在。不篩的話這一步會放行，然後在主機上
  pull 一個沒有人建過的 tag。
- **它靠 workflow 名稱找 run**（`gh run list --workflow CI`）。把 `ci.yml` 的 `name:` 改掉
  就永遠等不到，而症狀是「等待 CI 超時」，不會說「找不到那個 workflow」。

另外三件只在 workflow 檔裡、操作時會意外的事：

- **同時觸發兩次是排隊，不是取消**（`concurrency: cancel-in-progress: false`）。被取消的那次
  可能已經動過線上狀態了，所以寧可排隊。
- 整個 job 的上限是 **60 分鐘**，必須大於第 2 步自己的 30 分鐘。
- **`DEPLOY_HOST`／`DEPLOY_USER`／`DEPLOY_PATH` 與兩支 SSH secret 沒有存在性檢查。**
  漏設任何一個，訊息一律是第 4 步那句「連不上部署主機」。
  收到那句話時，先照上面「設完確認一次」把 environment 的 secret／variable 列出來看。

#### 部署成功長什麼樣

workflow 綠燈已經涵蓋兩層驗證（容器 healthy、對外連得到，判準見下一節），所以綠了就是成功。
但主機上有三件事**看起來像壞掉、其實正常**，第一次部署的人幾乎都會問：

**常駐容器是四個，不是五個。** `migrate` 是一次性工作（compose 裡 `restart: "no"`），
跑完就結束，而 `docker ps` 只列正在跑的。要看它的結果用 `docker ps -a` 或
`docker logs <專案名>-migrate`，`Exited (0)` 就是成功。

**不過通常不必看** —— `api` 起得來本身就是 migration 成功的證據。它對 `migrate` 的
`depends_on` 條件是 `service_completed_successfully`，migration 失敗時 api 根本不會啟動，
web 與 nginx 也會因為鏈式依賴而停在那裡，`/healthz` 打不通。

**`nginx` 沒有 `(healthy)` 是正常的。** 四個服務裡只有它沒定義 healthcheck
（`api`、`web` 與 `postgres` 都有），而沒定義的容器 `docker ps` 就只顯示 `Up` ——
那不是「不健康」而是「沒有人在探」。
nginx 的就緒由 `depends_on`（等 api 與 web 都 healthy）保證。

想自己再確認一遍：

```bash
cat <DEPLOY_PATH>/.deployed                 # 這一版真的服務過的紀錄，見下面
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Image}}'
docker image inspect <IMAGE_REGISTRY>/api:<tag> --format '{{index .RepoDigests 0}}'
```

最後那一條是 registry 模式的核心承諾：digest 要與 GHCR 上同一個 tag 的 digest 相同 ——
**線上跑的與 CI 綠燈的是同一份**，而不是「用同樣的原始碼再建一次」。`make prod` 給不了這個。

（同一份原始碼在不同 commit 上建出來的 digest **會不一樣**，因為 image 的 digest 也包含
`metadata-action` 打上去的 OCI label。所以比對的對象是「GHCR 上那個 tag」，不是「另一個 tag」。）

#### 部署失敗會自動回滾

部署失敗時 `deploy.yml` 會用同一條部署路徑退回上一版（工作樹與 image 一起退）。
四種失敗都算：image 拉不到、compose 起不來、新版**五分鐘內沒有變成 healthy**、
或健康了但**從外面連不到**。

判成敗的是 `scripts/deploy.sh` 自己 —— 它 `up -d` 之後會等 `<專案名>-web` 通過
healthcheck，再打一次 `http://127.0.0.1:$SYSTEM_PORT/healthz` 確認 nginx 這一層也通。
（healthcheck 探的是容器內部，繞過 nginx 與 port 綁定，而 nginx 模板正是每次部署會跟著
換的東西。）所以手動跑那條路也擋得住壞掉的版本，只是**不會**自動退回去。

##### 回滾標的來自 `.deployed`，不是工作樹

`deploy.sh` 在上述驗證都通過之後，才把這一版寫進主機的 `.deployed`：

```
DEPLOYED_COMMIT=<40 字元 commit SHA>
DEPLOYED_TAG=<image tag>
DEPLOYED_AT=<UTC 時間>
```

**這個檔案是回滾標的的唯一來源**，`deploy.yml` 只讀它。不去問 `git rev-parse HEAD` 是因為
那回答的是另一個問題（工作樹 checkout 到哪）—— 一次失敗且沒回滾成功的部署會把 HEAD 留在
壞掉的那一版，之後的「回滾」就會退到它。`.deployed` 裡的則必定是真的服務過的版本。

檔案在 `.gitignore` 裡，`git checkout --detach` 不會動到它。**不要手動編輯**：內容形狀不對
（commit 不是 40 字元 hex、tag 空）時 `deploy.yml` 會當成沒有紀錄而跳過回滾。

回滾成功之後這次 workflow 仍然算**失敗**。線上被救回來了，但這次發版沒有成功，
兩件事不該混在一起看。

三種情況不會自動回滾：

- **主機上沒有有效的 `.deployed`**（全新主機、第一次部署）—— 留 warning 然後繼續。
  沒有已知的好版本時，硬退到一個沒驗過的 commit 比停在原地更糟。
- **連不上主機** —— 這是**錯誤**，整個部署當場中止，不會往下走。它跟上一項是不同的事，
  混成同一個結果的話，一次暫時性的連線失敗會安靜地讓這次部署失去安全網。
- **失敗發生在部署那一步之前**（ref 解不開、CI 沒綠、SSH 探不到）—— 那時工作樹與容器都
  還沒被動過，退版只會多一次沒必要的重啟。步驟編號見上面的「Deploy workflow 做了什麼」。

回滾**不會再 `git fetch` 一次**，它直接 checkout `.deployed` 裡那個 commit。正常情況下
那一版本來就在主機的 object store 裡（它剛剛還在服務），但如果有人在主機上跑過
`git gc --prune` 之類的東西把它清掉了，回滾會在 checkout 那步失敗。

> **回滾期間會有停機**
>
> compose 沒有內建的滾動更新，`up -d` 是把舊容器換掉。所以無論正向部署或回滾，
> nginx 都會有一段時間 502。單機架構要消掉這段得在 nginx 前面再加一層。

> **回滾不會回滾資料庫**
>
> `migrate` 容器只跑「未套用」的 migration（`apps/api/shared/db/migration.py` 的
> `run_pending`），**沒有 down migration**。所以退版之後 DB 停在新 schema、程式碼是舊的。
>
> 啟動鏈那句「新版程式碼配上舊資料結構在機制上不可能出現」只對**向前**成立；
> 反方向沒有任何機制在擋。會改動既有欄位語意的 migration，發版前要先想清楚退路 ——
> 通常是讓那一版的程式碼能同時讀新舊兩種形狀，退版才有意義。

> **為什麼 `make deploy` 不會退回本機建置**
>
> `scripts/deploy.sh` 帶 `--no-build`。少了它，image 拉不到時 compose 會**安靜地**
> 改用 build context 就地建一份 —— 那就完全繞過了「部署 CI 驗過的那一份」，
> 而且看起來一切正常。

#### registry 模式唯一的 build 期值

前端絕大多數設定都已經是執行期注入（`apps/web/shared/runtime/config.ts`），
所以同一份 image 可以部署到任何環境。剩下兩個結構上移不掉：

**`UPLOAD_SIZE_LIMIT`** —— Next 把它序列化進 `.next/required-server-files.json`，
standalone 執行期不會重新求值 `next.config.ts`。它同時以執行期環境變數送進容器，
`apps/web/instrumentation.ts` 在啟動時比對兩者，不一致就印出原因並**結束行程**。
所以 GitHub variable 的 `UPLOAD_SIZE_LIMIT` 要與主機 `.env` 的一致；忘了同步不會靜靜地錯，
而是 web 進入重啟迴圈 —— nginx 等不到它 healthy，部署停在那裡，不會有半套的服務上線。

> 那一步刻意用 `process.exit` 而不是拋錯：實測 Next 會接住 instrumentation hook 的例外
> 並**讓伺服器繼續監聽**，對每個請求回 500。那個狀態下 `docker ps` 看起來是 Up，
> 只有 healthcheck 會紅 —— 等於把可見度外包給那份 healthcheck 還在不在。

**`NEXT_SERVER_ACTIONS_ENCRYPTION_KEY` 不再是其中之一。** 它曾經也是 build 期值
（而且是整份清單裡唯一一個 `make check-env` 守不到的同步點），現在 image 裡只有一個
公開的 id salt，真金鑰由 compose 在執行期注入 —— 所以它跟其他秘密一樣，只住在主機的
`.env`，改了重啟即可。理由與實測見 [`../apps/web/Dockerfile`](../apps/web/Dockerfile) 的長註解。

歷史留在這裡是因為代價還在，只是換了位置：**重建 image 會讓所有 Server Action id 改變**
（salt 是常數，但程式碼變了 id 就變），使用者開著沒重載的分頁按下按鈕會拿到
「Server Action ... was not found on the server」。所以它設一次就不要動 ——
輪換它跟輪換 `JWT_SECRET_KEY` 不一樣，後者只是要大家重新登入。

#### 這條 CD 刻意沒有做的事

**這是刻意的範圍，不是還沒做。** 七件事在別的專案裡常見，這裡沒有：

**沒有把分支保護寫進這條 CD。** `main` 的保護是三層（ruleset 在伺服器端擋、
`.githooks/pre-push` 在本機擋、CI 的 `pushed-via-pr` job 事後吵），但 ruleset 是 repo 設定、
不在版控裡，所以 CD 這一側不會、也沒辦法確認它在。細節見
[`development.md`](development.md#分支保護)。

**沒有 staging。** 只有 `production` 一個 environment：合進 `main` 與打 tag 都只是把 image
推上 registry，而唯一的上線動作直接打在正式環境上，中間沒有一個「先部署到別的地方看看」的
環節。要加的話是複製一份 `deploy.yml`、換一組 `DEPLOY_*` variables 並改觸發條件
（例如 push 到 `main` 就部署 staging），`scripts/deploy.sh` 本身不必動 —— 要部署哪個 tag
由呼叫端當參數給，registry 與其餘設定讀主機自己的 `.env`。

**只建 linux/amd64。** `publish` 的兩個建置步驟都沒有指定平台，出來的就是 runner 的原生
架構。**部署主機是 arm64 的話 image 拉得下來、跑不起來**，而同一台主機上 `make prod` 卻是
好的（就地建置用的是主機自己的架構）—— 症狀不會指回這裡，所以先知道。要多平台就在那兩步
加上 `platforms`，代價是 arm64 那一份走 QEMU 模擬，`publish` 的時間大約會變成兩到三倍，
web image 的 `next build` 尤其慢。

**沒有 image 層的漏洞掃描。** `security` job 查的是 npm 與 uv 相依的已知漏洞
（範圍見 [`development.md`](development.md#安全-advisory)），base image 裡的 OS 套件不在裡面。

**沒有 provenance 與 SBOM。** 推上去的是純 image，沒有附建置來源的簽章或料件清單。

**這一條靠明寫維持**：`docker/build-push-action` 從 v6 起，push 時**預設**會掛上 min 模式的
inline provenance，所以 `publish` 的兩個建置步驟都寫了 `provenance: false`。拿掉那兩行的話
image 就不再是純 image 了，而這件事從 workflow 檔面上看不出來 —— 要翻 buildx 的指令列才知道。

要做的話：把那兩處改成 `provenance: mode=max`、加上 `sbom: true`，再給 job 一個
id token 的權限，不會動到現有流程 —— 記得連這一節一起改。

**`latest` 這個 tag 不是「最新的一次建置」。** 它由 `metadata-action` 的 `latest=auto`
掛在**語意化版號**上，所以只有推 `v*` tag 才會移動；`main` 上的每一次合併都推了 image，
但 `latest` 不會跟著走。想拉「最新一次合併」請用 `main` 或 `sha-<short>`。

**部署後只有 smoke test。** `scripts/deploy.sh` 打一次 `/healthz`，通了就算成功 ——
沒有金絲雀、沒有指標比對，**也不會在正式環境跑 e2e**（e2e 在 CI 上對著一套隔離的 stack
跑，見 [`development.md`](development.md#規格與測試的三層) 的「e2e 的範圍」）。
這也是自動回滾唯一的判準，所以「回滾機制沒被觸發」不等於「這一版是好的」。

（部署期間會斷線、以及回滾不會回滾資料庫，是另外兩件事，寫在上面那兩個引用區塊裡。）

### 應用層的可觀測性只到 stdout

**這是刻意的範圍，不是還沒做。** 後端提供的是 `app/server.py` 那個 middleware 寫到 stdout
的請求紀錄（方法、路徑、狀態碼、耗時；**不含 query string**，理由見該處註解），
加上三個服務的 Docker healthcheck。就這些。

探活路徑不列入請求紀錄，清單在 `app/server.py` 的 `UNLOGGED_PATHS`（目前只有 `/health`）。
healthcheck 每 10 秒打一次，記下來只會把真正的請求淹掉，而「服務還活著嗎」已經由
`docker compose ps` 的健康狀態回答了。這份清單**只放探活路徑** —— 它一旦長出第二種用途，
就變成「某些請求悄悄不留紀錄」的後門。web 的探活端點同理走 `apps/web/app/healthz/route.ts`
這支常數回應，而不是任何真實頁面（頁面會 server-render 並回頭打 API）。

**有** request／correlation id：每一行請求紀錄開頭的 `[xxxxxxxx]`。它由 nginx 的
`$request_id` 產生（兩份模板都以**覆寫**方式設定 `X-Request-ID`，用戶端偽造不了），
經 Next 伺服器端原樣往後端傳（`apps/web/shared/api/headers.ts`），後端寫進 log 並回寫到
回應標頭。所以**同一次使用者操作在三個行程的紀錄裡是同一個 id**，使用者回報問題時
把回應標頭裡的值給你就能直接對到 log，不必靠時間戳猜。

直接打 api（沒有經過 nginx）時後端會自己產一個；外部帶進來的值會先過
`shared/http/context.py` 的清洗（長度與字元），因為它會被寫進 log ——
帶換行的值可以偽造出一整行假的請求紀錄。

**沒有**的東西，需要時要自己接：結構化（JSON）log、錯誤追蹤（Sentry 之類）的接點、
指標輸出。選擇停在這裡是因為這幾樣的正確做法高度依賴你的部署平台 ——
模板先綁一套，多數專案第一件事會是把它拆掉。而 request id 相反：它幾乎不依賴平台，
卻要在每個模組開始各自 logging **之前**就定案，事後補的代價高得多。

因此**日誌保存與查詢是部署層的事**：容器的 stdout 由 docker 的 json-file driver 收，
正式環境已設好轉檔上限（`infra/docker/docker-compose.prod.yml` 的 `x-prod-runtime`），
但**不會**自動送到任何地方。要留存或搜尋請自行接上平台的 log driver 或 sidecar。

## 資料庫 migration 何時執行

**部署時自動執行，不需要手動介入**（上面的啟動鏈）。撰寫 migration 的方式見
[`extending.md`](extending.md#資料庫-migration)。

`make migrate` 是給維運與驗證用的，不是部署流程的一部分：

```bash
make migrate    # 對目前運行中的環境執行未套用的 migration
```

它用 `compose run --rm migrate` 起一個一次性容器，migration runner 本身**不需要** api
行程正在執行。但 `make migrate` 會從既有的 api container 讀取 `MODE`，所以 api container
必須仍存在。剛執行過 `make down` 的話，請先啟動對應環境，或直接以正確的 `MODE` 執行
compose 指令。

## 首次初始化：建立第一個超級管理者

系統還沒有超級管理者時，**進站會自動落在 `/signup`**（手動輸入 `/login` 也會被導過去）。
填入 `.env` 裡的 `REGISTER_KEY` 建立第一個超級管理者帳號。

**這件事一個部署只能成功一次。** 完成之後：

- `/signup` 永久導回 `/login`，登入頁上也不再有任何註冊入口
- 即使拿著正確的 `REGISTER_KEY` 直接打 API，也會得到 `409`
- `REGISTER_KEY` 從此失效，可以從 `.env` 清空（留空代表完全停用這條路徑）

之後的帳號一律由超級管理者在「使用者管理」頁面建立。

> **為什麼要這樣設計**
>
> 這是自架系統常見的 first-run setup 形狀：未初始化時所有入口都指向 setup，完成後那條路徑
> 永久關閉。前端只做「顯示什麼」的決定，真正的把關在後端 —— `system_state` 資料表的
> 唯一約束會與使用者在同一個交易內建立，因此併發請求最多一個成功，使用者建立失敗時
> guard 也會一起回滾。
>
> 後端查不到初始化狀態時（例如後端剛好在重啟），登入頁**留在原地**、註冊頁**照樣顯示表單**
> —— 兩頁對「不確定」的安全方向相反，所以狀態是三態而不是布林值。

### 需要第二個超級管理者，或帳號失聯時

網頁註冊只能成功一次，所以另外提供一條 CLI：

```bash
make create-superuser
```

互動式輸入帳號、暱稱與密碼（密碼以 `getpass` 讀取，不回顯、也不進 shell history），
建立一個擁有全部權限的帳號。用途有兩個：唯一超管失聯時的救援，以及需要多個超管的場景。

- 它同時會補上初始化旗標，因此**執行之後 `/signup` 一律關閉** —— 用 CLI 完成初始化的部署
  不會留著一條公開的建號路徑。
- 對已初始化的系統可以重複執行，每次多一個超級管理者。
- 刻意做成 CLI 而不是「再發一組一次性註冊碼」：後者會把一條公開、未登入、能造出全權限帳號
  的端點長期留在網路上。這裡的授權模型是「你已經能 exec 進伺服器容器」，那個權限本來就大於
  系統內任何帳號。

一般管理者不需要走這條路 —— 在「角色管理」建立一個帶所需權限的角色，再於「使用者管理」指派即可。

## 角色與權限模型

模板預設只建立一個內建角色：

| 角色 code | 名稱 | Permission | 可做什麼 |
|---|---|---|---|
| `super_admin` | 超級管理者 | `*`（所有） | 建立/停用使用者、重設密碼、管理角色、所有操作 |

建立使用者時若未指定角色，會以沒有角色與沒有額外權限的狀態建立。專案若需要 `member`
或其他預設角色，可在 `RoleTable.seed_data` 新增（見
[`extending.md`](extending.md#初始資料seed)）。

`super_admin` 角色**不能經由 API 指派**：`modules/users/service.py` 的
`validate_role_ids()` 無條件拒絕任何帶
`Permission.ALL` 的角色，`Permission.ALL` 也不在 `GET /permissions/` 的目錄裡。因此擁有它的
帳號只有兩個來源：一次性的網頁初始化，以及 `make create-superuser`。需要「幾乎等同超管」的
管理者時，建立一個帶所需權限的角色即可 —— 差別只在 `*` 會自動涵蓋日後新增的權限。

## Session 撤銷

認證有兩層版本號，用途不同：

| | 存在哪 | 作用範圍 | 什麼時候會變 |
|---|---|---|---|
| `TOKEN_VERSION` | `.env`（環境變數） | **所有人** | 手動 +1，例如 `JWT_SECRET_KEY` 外洩 |
| `auth_version` | `users` 文件 | **單一使用者** | 重設密碼時自動 `$inc` |

重設密碼會在同一個資料庫操作裡換掉密碼並把 `auth_version` +1，於是那個人所有既有的
session token 與 WebSocket ticket 在下一次請求就被拒絕（401）。

這讓管理者重設密碼時能立刻撤銷遭入侵帳號既有的登入憑證，而不影響其他使用者。

### Session 不會續期，`EXPIRE_HOURS` 是硬上限

**沒有 refresh token，也沒有「有在操作就自動延長」。** `EXPIRE_HOURS` 同時決定 JWT 的 `exp`
與 cookie 的 `maxAge`（`apps/web/modules/auth/actions.ts`），時間到就是 401 導回 `/login`，
不管使用者當下正在做什麼。

代價很具體：`EXPIRE_HOURS=8` 的部署，早上九點登入的人下午五點按下「儲存」會被踢回登入頁，
表單內容跟著消失。**請依你的使用情境調整這個值**，把它當成「使用者最長多久要重新登入一次」
來設，而不是「閒置多久登出」—— 它跟閒置與否無關。

之所以停在這裡：滑動續期要嘛得引入 refresh token（多一組憑證、多一條撤銷路徑），要嘛得讓
每個請求都可能改寫 cookie（Server Component 讀得到 cookie 但寫不了，得繞到 middleware 或
Server Action）。兩種做法都會把上面「Session 撤銷」那張表變複雜，而多數內部系統把
`EXPIRE_HOURS` 設長一點就夠了。

要做的話它是一個獨立改動，不需要動 `shared/auth`：新增一條「以舊 token 換新 token」的端點，
沿用現有的 `auth_version` 檢查，前端在 token 剩餘時間低於某個比例時呼叫它並改寫 cookie。

### 密碼重設沒有自助流程

**只有管理者能重設別人的密碼**，使用者忘記密碼時無法自己救回來 —— 模板沒有 email／SMTP
設定，也就沒有「寄重設連結」這條路。這是刻意的：一條未登入就能觸發的信件發送端點，
需要配上寄件網域、退信處理與它自己的限流，而那些在內部系統裡通常不划算。

代價是**忘記密碼一律要找管理者**，請在上線前確認你的使用者知道要找誰。唯一超管自己失聯時
的救援路徑是 `make create-superuser`（見上方「需要第二個超級管理者，或帳號失聯時」）。

要加自助重設的話，它是一個新的 module，不需要動 `shared/auth`：重設完成後照上表把該使用者的
`auth_version` +1，既有 session 就會一起失效。

## 用戶端 IP 與限流

登入與註冊以用戶端 IP 限流（`shared/http/rate_limit.py`）。IP 從哪裡取，決定了限流擋不擋得住。

**目前的設定假設 nginx 就是最外層。** nginx 以 `$remote_addr` **覆寫** `X-Real-IP` 與
`X-Forwarded-For`，後端只讀 `X-Real-IP`，所以用戶端送什麼進來都會被蓋掉。
那兩份模板共六個 proxy location 全部都要這樣寫，由 `make check-nginx` 守著 ——
漏一個 location 不會有任何錯誤訊息，只會讓那條路徑上的人共用同一個限流 key。

**如果 nginx 前面還有一層 proxy**，直接沿用目前設定會讓 `$remote_addr` 變成那層 proxy 的位址，
於是**所有使用者共用同一個限流 key**（一個人打爆，全站被鎖）。這時要在
`infra/nginx/templates/default.conf.template` 改用 `ngx_http_realip_module`：

```nginx
set_real_ip_from  10.0.0.0/8;   # 換成你的 LB／CDN 實際的 CIDR
real_ip_header    X-Forwarded-For;
real_ip_recursive on;
```

它會把 `$remote_addr` 修正成真實用戶端位址，`proxy_set_header` 那兩行維持不變即可。
**`set_real_ip_from` 一定要填實際的信任範圍**，填 `0.0.0.0/0` 等於把偽造的洞原封不動地開回來。

限流本身是行程內的（多副本時各算各的），這是刻意的取捨，詳見 `shared/http/rate_limit.py`
的模組註解。

## 備份與還原

```bash
make backup     # 備份目前資料庫到主機的 ./backups/*.dump（pg_dump 的 custom 格式）
make restore    # 列出 ./backups/ 的備份，互動式選擇並在確認後還原
```

`./backups/` 由 `make backup` 在備份成功之後才建立 —— 容器沒有掛任何主機目錄，
備份檔是由腳本串流進出的（理由見 `scripts/backup.sh` 的檔頭）。所以在還沒備份過的專案裡
看不到這個目錄是正常的，`make restore` 這時會直接退出並提示先跑 `make backup`。

備份檔留在主機上，**不會隨容器一起消失，但也不會自動異地保存**。
正式環境請另外安排排程與異地複製，並定期做一次真實的還原演練 ——
沒有演練過的備份等於沒有備份。
