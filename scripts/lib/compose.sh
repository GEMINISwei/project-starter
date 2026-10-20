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
# 所以每一支會呼叫這裡的腳本都要先 `require_env` (訊息會指回「先跑 make init dev|prod」) ——
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

# 依 .env 的 MODE 疊 overlay: development 是 bind mount 的原始碼, production 是建置或拉好的 image。
# MODE 由呼叫端先載入 (load_env); 這裡不載: `make check lint` 用 .env.example 驗證時, MODE
# 是從呼叫端直接給的, 載入真的 .env 會把它蓋掉。
app_compose() {
    require_mode
    local overlay=dev
    if [ "${MODE}" = production ]; then
        overlay=prod
    fi
    NGINX_CONFIG_HASH="$(nginx_config_hash)" \
        compose -f "$COMPOSE_DIR/docker-compose.${overlay}.yml" "$@"
}

# nginx 的模板與片段是 bind mount 的, 內容變了 compose 看不出來, `up` 不會重建 nginx; 而官方
# image 只在啟動時展開模板, 所以線上會一直跑舊設定, 直到哪天重開機才突然換成新的 (實測過:
# api 與 web 被重建時 nginx 也不會跟著重建)。把內容的雜湊放進 nginx 的 label, 變了就重建。
#
# 整個目錄一起算, 不分 MODE: 只改另一種模式的模板會多重建一次, 換來不必跟 overlay 對齊。
# 用 cksum 是因為 POSIX 必備, macOS 與 Linux 主機都有; 這裡防的是漏改, 不是竄改。
nginx_config_hash() {
    (cd "$REPO_ROOT/infra/nginx" && find . -type f | LC_ALL=C sort | xargs cksum | cksum) \
        | awk '{ print $1 }'
}

# 用法: container_running <容器名稱>
#
# 先把清單存下來再比對, 不直接接 `| grep -q`: grep 提早結束會讓 docker 收到 SIGPIPE, 在 pipefail
# 下整條管線算失敗。docker 本身失敗要明確 exit, 不能當成「沒在跑」。
container_running() {
    local names
    names="$(docker ps --format '{{.Names}}')" || { echo "無法列出 docker 容器" >&2; exit 1; }
    grep -qx "$1" <<< "${names}"
}

# 用法: without_traffic <指令...>
#
# 停掉 nginx (唯一的對外入口) 再執行指令, 結束後 (失敗也一樣) 開回來: 備份與還原期間沒有新的
# 寫入, 資料庫與上傳檔案才是同一個時間點。用 stop 不用 down, 容器原樣留著。
#
# nginx 本來就沒在跑時什麼都不動, 只開回自己停掉的: 還原會在外層先停, 裡面那次備份不能在還原
# 之前就把它開回來。
#
# 用 EXIT trap 而不是 `"$@" || status=$?`: 在 `||` 左邊的函式裡 `set -e` 不生效, 中途失敗會繼續
# 往下跑。這個 trap 會取代呼叫端的 EXIT trap, 所以呼叫端不能自己再設一個。
without_traffic() {
    local nginx="${COMPOSE_PROJECT_NAME}-nginx"
    if ! container_running "${nginx}"; then
        "$@"
        return
    fi
    echo "停止對外服務（${nginx}），完成後會重新啟動"
    docker stop "${nginx}" > /dev/null
    # shellcheck disable=SC2064 # 現在就展開: trap 觸發時這個區域變數已經不在了
    trap "docker start '${nginx}' > /dev/null" EXIT
    "$@"
    trap - EXIT
    docker start "${nginx}" > /dev/null
    echo "已重新啟動對外服務"
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
# 舊版只有 `docker-compose`、或 Docker Desktop 沒開時, 錯誤要到 `make start` 才出現。
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

# 用法: default_project_name <目錄>
#
# `make init` 問專案名稱時的預設值: 同主機多套系統時, 目錄與專案同名最好對照。
# 轉成專案名稱的字元集 (小寫英數、-、_), 轉完什麼都不剩 (例如全是中文) 才退回 my-app。
# LC_ALL=C: 讓多位元組字元逐 byte 被當成不合法字元, 不會因 locale 而被 [a-z] 意外收下。
default_project_name() {
    local name
    name="$(basename "$1" | LC_ALL=C tr '[:upper:]' '[:lower:]' \
        | LC_ALL=C sed 's/[^a-z0-9_-]\{1,\}/-/g; s/^[-_]*//; s/[-_]*$//')"
    printf '%s\n' "${name:-my-app}"
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
