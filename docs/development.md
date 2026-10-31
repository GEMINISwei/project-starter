# 開發指南

本機環境、指令與程式碼風格。測試見 [`testing.md`](testing.md)，開發流程與提交見
[`workflow.md`](workflow.md)，擴充功能見 [`extending/`](extending/README.md)，部署與維運見 [`operations.md`](operations.md)。

## 開發環境

需要 Docker Desktop、`make`、`openssl`、`uv` 與 Node.js（版本見 [`apps/web/.nvmrc`](../apps/web/.nvmrc)；
升 Node 時 `apps/web/Dockerfile` 的 `ARG NODE_VERSION` 要手動跟上）。

```bash
make init dev   # 產生 .env（MODE=development，金鑰自動產生）、安裝相依、git init
make start      # 啟動 postgres → migrate → api → web → nginx（首次建置約 2–5 分鐘）
```

環境起來之後用 `make db superuser` 建立第一個帳號（網頁上沒有註冊入口），再打開
`http://localhost:{SYSTEM_PORT}`（預設 3000）登入。`migrate` 停在 `Exited (0)`、`nginx` 沒有 `(healthy)`
都是正常的。

### 用手機測試

```bash
make start lan  # 同 make start，但對區網開放，結束時印出手機要開的網址
```

平常 nginx 只綁 `127.0.0.1`，手機連不進來。`make start lan` 只在這次啟動改綁 `0.0.0.0`，
下次一般的 `make start` 就關回去，所以**用完跑一次 `make start`**；`.env` 裡沒有對應的設定，刻意不讓它常駐。
開著的時候同一個網路上的人都連得到，在公共 Wi-Fi 上不要用。`MODE=production` 時會被拒絕。

只能用 `http`：瀏覽器只對 `localhost` 放寬安全來源的限制，相機、定位、Service Worker 這類需要 HTTPS 的功能
在 `http://<區網 IP>` 上不能用，要測的話改用會給 https 網址的 tunnel（cloudflared、Tailscale Funnel）。

### 環境變數的同步點

新增環境變數要改這幾處：

| 位置 | 作用 | 漏了的話 |
|---|---|---|
| `.env.example` | 清單，也是 `make init` 產生 `.env` 的範本 | compose 用了 `${X:?}` 卻不在這裡：`make check lint` 擋 |
| `infra/docker/docker-compose.yml` | 注入容器 | **不會報錯**，症狀是「設了卻一直用預設值」 |
| `apps/api/app/config.py`／`apps/web/shared/runtime/config.ts` | 讀取端（哪一邊用就改哪一邊） | 同上 |
| `scripts/init.sh` | **只有**要詢問使用者或自動產生祕密的才改，有固定預設值的直接寫在範本 | 範本裡的空值原樣進 `.env` |

### 起不來的時候

| 症狀 | 怎麼辦 |
|---|---|
| `port is already allocated` | 改 `.env` 的 `SYSTEM_PORT`，`make services down && make start` |
| api 一直重啟、`relation "users" does not exist` | migration 失敗了，`make services logs migrate` 看原因 |
| 容器裡 `ModuleNotFoundError` | 改了相依但 image 沒重建，重建後再 `make start` |
| api 一直重啟、`password authentication failed` 或 `role "app" does not exist` | 資料庫的帳號密碼只在第一次建立 volume 時寫入：改過 `.env` 的 `POSTGRES_PASSWORD`，或 volume 是舊版（帳號不是 `app`）建的。開發機可以清掉重建（**資料會消失**）：`make services down`，`docker volume rm <專案>_development_postgres_data`，再 `make start` 與 `make db superuser` |
| `make init dev` 抱怨 Node 版本 | `nvm use` |
| `make init dev` 說專案名稱已有 docker 服務在使用 | 換一個名稱；確定是不要的舊專案，就用 `docker rm`／`docker volume rm` 清掉列出的資源 |

## 指令

一個主題一個指令，第二個字選動作。完整說明看 `make help`：

```bash
make init dev|prod                           # 產生 .env 並寫入 MODE；prod 只產生 .env（部署主機用）
make start [lan]                             # 依 .env 的 MODE 啟動；lan = 開放區網讓手機連（僅 development）
make services [volumes|logs [服務]|restart|down]   # 不帶參數 = 版本與 MODE、服務狀態、volume；restart = 原地重啟
make backup                                  # 資料庫與上傳檔案一起備份，期間對外服務暫停
make db   psql|restore [檔案]|reset|migrate|migration "說明"|superuser
make uploads restore [檔案]
make check [lint|contract|migrate|types|test|build|integration|e2e]   # 不帶參數 = 前六項，送出前跑
make gen-types                               # 改過後端 schema／權限／語系後必跑
```

**`MODE` 決定這台主機是哪種環境。** `make init dev|prod` 寫進 `.env`，只在第一次產生時決定；
要換就刪掉 `.env` 重跑，或手動改那一行。`make start` 依它疊 dev 或 prod 的 overlay，缺少或不是
`production`／`development` 時，碰容器的指令一律停下來。開發機要驗證 production build，就暫時改成
`MODE=production`（volume 名稱帶著 `MODE`，開發資料不會被動到），驗完改回來。
`MODE=production` 時擋下的指令見 [`operations.md`](operations.md#生產部署)。

實作在 `scripts/<指令>.sh`，可以直接執行（`./scripts/db.sh psql`）。新增子指令＝改那支腳本的
`case`，並在檔頭補一行 `#   make …`（`make help` 讀的就是它）；新增指令＝加一支腳本並把名稱
加進 Makefile 的 `TARGETS`。部署與腳本自己用的指令寫成 `#   [內部] make …`，不列在 help，
只寫在 [`operations.md`](operations.md#內部指令)。

## 程式碼風格

由 lint 擋的上限（防退步的地板，不是重構目標）：

| 規則 | 前端 `.ts` | 前端 `.tsx` | 後端 |
|---|---|---|---|
| 單行長度 | 100 字元 | 100 字元 | 100 顯示寬度（中文算 2） |
| 巢狀深度 | 4 | 4 | — |
| 循環複雜度 | 10 | 15 | 10 |
| 函式長度 | 60 行 | 100 行 | 40 敘述 |

靠 review 的：

- **一個函式一件事**：需要用「而且」才描述得完，就該拆。
- **早退出**：前置條件不成立就 `return`。
- **命名見義**：讀不出意圖的長布林運算式，給它一個名字。
- **不留死碼**：註解掉的程式碼、「之後可能會用到」的分支一律刪掉。

### 註解與文件

註解寫**為什麼**，不寫做了什麼 —— 尤其是「為什麼不用另一種看起來更自然的做法」。一個取捨一段，
講完就停；演進過程寫進 commit message。註解與文件用繁體中文，技術名詞保持原文。
程式碼裡的註解與 docstring 用**半形標點**（`, : ; ( ) ? /`，逗號、冒號後面空一格）：全形的
`，：（）` 會被編輯器標成「可能與 ASCII 字元混淆」。Markdown 文件與使用者看得到的字串（i18n、
終端訊息、測試名稱）維持全形。
文件**一個主題一個 owner**，其他地方只放連結；範例指向 repo 內的真實檔案。
