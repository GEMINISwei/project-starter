#!/usr/bin/env bash
#
# docker compose 的旗標組合與模式偵測。所有碰容器的腳本都 source 這一支。
#
# 這裡是 compose 旗標的**唯一來源**, 不要在別處再組一份: 旗標飄掉的時候 docker
# 不會報錯 (理由見下方說明), 所以「兩份看起來都對」正是最危險的狀態。

# shellcheck source=scripts/lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

COMPOSE_DIR="$REPO_ROOT/infra/docker"
readonly COMPOSE_DIR

# ── compose 的路徑解析 (實測結論, 動這幾行之前請先讀完) ─────────────────────────
#
# `--project-directory` 同時決定兩件事:
#   (1) compose 檔裡的相對路徑 (build.context、bind mount 的 source) 以它為基準
#   (2) `.env` 的自動探索位置
# 而 `--env-file` 是以**呼叫時的 CWD**為基準, 且會**取代** (而非補充) (2) 的自動探索。
#
# 我們要的組合是: 相對路徑以 infra/docker 為基準 (compose 檔裡才能寫 `../../apps/api`),
# 但 `.env` 讀 repo 根目錄那一份。只有這組旗標能同時滿足兩者。
#
# 全部用 $REPO_ROOT 展開成絕對路徑, 從任何 CWD 呼叫都不會壞 ——
# 相對路徑的話 --env-file 會跟著呼叫者的 CWD 跑掉。
#
# **`--env-file` 指到不存在的檔案時 compose 一定失敗**, 而且不會退回讀環境變數。
# 所以每一支會呼叫這裡的腳本都要先 `require_env` (訊息會指回「先跑 make init」) ——
# 少了那一步, 錯誤會落在呼叫端自己的錯誤路徑上, 變成跟原因無關的東西。
# 守衛不放在這個函式裡: 呼叫端多半是 `$(compose config ...)`, 命令替換裡的 `exit`
# 只結束子 shell, 主腳本會若無其事地拿著空字串繼續跑。
#
# COMPOSE_ENV_FILE 只給 `make check lint` 用: 它拿 .env.example 驗證 compose 檔,
# 不需要 (也不該讀) 真的 .env。
compose() {
    docker compose \
        --project-directory "$COMPOSE_DIR" \
        --env-file "${COMPOSE_ENV_FILE:-$REPO_ROOT/.env}" \
        -f "$COMPOSE_DIR/docker-compose.yml" \
        "$@"
}

dev_compose() {
    MODE=development compose -f "$COMPOSE_DIR/docker-compose.dev.yml" "$@"
}

prod_compose() {
    MODE=production compose -f "$COMPOSE_DIR/docker-compose.prod.yml" "$@"
}

# `make dev` 與 `make prod` 的共同實作: 同一組子指令, 只差 compose 疊的是哪一份 overlay。
#
# prod 的 up 預設 `--build`: 正式環境要確定跑的是目前這份原始碼建出來的 image;
# dev 不必, 原始碼是 bind mount 進去的, 改了直接生效。
#
# 有給 API_IMAGE/WEB_IMAGE (deploy workflow 從 CI 建好的 image) 時改成拉 image, 而且
# **不能帶 `--build`**: 實測 `--build` 會蓋過 `pull_policy: always`, 照樣在主機上建置,
# 還把建出來的東西標成 registry 的 image 名稱。兩個要一起給 —— 只給一個的話, 另一個會去
# Docker Hub 拉 `<專案>-web:latest` 之類不存在的 image。
stack() {
    local mode="$1" action="${2:-up}"
    shift 2 || shift $#

    load_env
    require_env COMPOSE_PROJECT_NAME

    local run="${mode}_compose"
    case "${action}" in
        up)
            if [ "${mode}" = prod ] && [ -n "${API_IMAGE:-}${WEB_IMAGE:-}" ]; then
                require_env API_IMAGE WEB_IMAGE
                IMAGE_PULL_POLICY=always "${run}" up -d --remove-orphans
            elif [ "${mode}" = prod ]; then
                "${run}" up -d --build --remove-orphans
            else
                "${run}" up -d --remove-orphans
            fi
            echo "已啟動：http://localhost:${SYSTEM_PORT}"
            ;;
        down) "${run}" down --remove-orphans ;;
        # 不帶服務名稱時看全部; `make dev logs api` 只看 api。
        logs) "${run}" logs -f --tail=200 "$@" ;;
        ps)   "${run}" ps ;;
        *)
            echo "用法：make ${mode} [up|down|logs [服務]|ps]" >&2
            exit 1
            ;;
    esac
}

# api 容器裡的資料庫 CLI (apps/api/scripts/db.py)。
db_cli() {
    docker exec -w /app "${COMPOSE_PROJECT_NAME}-api" python scripts/db.py "$@"
}

# 需要互動輸入的子指令用這個 (create-superuser 走 getpass, 沒有 TTY 會直接失敗)。
db_cli_tty() {
    docker exec -it -w /app "${COMPOSE_PROJECT_NAME}-api" python scripts/db.py "$@"
}

# `make init` 用: compose 外掛與 daemon 都要能用。只檢查 `docker` 指令在不在不夠 ——
# 舊版只有 `docker-compose`、或 Docker Desktop 沒開時, 錯誤要到 `make dev` 才出現。
require_compose() {
    if ! docker compose version > /dev/null 2>&1; then
        echo "缺少 docker compose（Compose v2 外掛，Docker Desktop 已內建）" >&2
        return 1
    fi
    if ! docker info > /dev/null 2>&1; then
        echo "無法連上 docker daemon：請先啟動 Docker；Linux 上確認目前帳號在 docker 群組（加入後要重新登入）" >&2
        return 1
    fi
}

# 用法: require_unused_project_name <專案名稱>
#
# 容器、volume、network 都以專案名稱為前綴, 撞名時新專案會接手舊專案的容器與資料庫 volume。
# 以 compose 的專案標籤比對而不是名稱前綴: `my-app` 與 `my-app-2` 是兩個專案。
# 容器含已停止的 (-a); volume 單獨也要擋 —— 容器刪了資料還在, 起來就是舊資料庫。
# 查詢失敗時中止, 不當成沒人用: 那正是會安靜撞名的情況。
require_unused_project_name() {
    local name="$1" filter="label=com.docker.compose.project=$1" containers volumes
    containers="$(docker ps -a --filter "$filter" --format '{{.Names}}')" \
        || { echo "無法列出 docker 容器，沒辦法確認專案名稱是否已被使用" >&2; return 1; }
    volumes="$(docker volume ls --filter "$filter" --format '{{.Name}}')" \
        || { echo "無法列出 docker volume，沒辦法確認專案名稱是否已被使用" >&2; return 1; }
    [ -z "${containers}${volumes}" ] && return 0

    local item
    {
        echo "專案名稱「${name}」已有 docker 服務在使用，請換一個名稱："
        for item in $containers; do echo "  Container  $item"; done
        for item in $volumes; do echo "  Volume     $item"; done
        echo "確定那些已經不要了，可以先用 docker rm／docker volume rm 清掉再重跑。"
    } >&2
    return 1
}
