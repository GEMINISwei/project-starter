#!/usr/bin/env bash
#
# docker compose 的旗標組合與模式偵測。所有碰容器的腳本都 source 這一支。
#
# 這裡是 compose 旗標的**唯一來源**，不要在別處再組一份：旗標飄掉的時候 docker
# 不會報錯（理由見下方說明），所以「兩份看起來都對」正是最危險的狀態。

# shellcheck source=scripts/lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

COMPOSE_DIR="$REPO_ROOT/infra/docker"
readonly COMPOSE_DIR

# ── compose 的路徑解析（實測結論，動這幾行之前請先讀完）─────────────────────────
#
# `--project-directory` 同時決定兩件事：
#   (1) compose 檔裡的相對路徑（build.context、bind mount 的 source）以它為基準
#   (2) `.env` 的自動探索位置
# 而 `--env-file` 是以**呼叫時的 CWD**為基準，且會**取代**（而非補充）(2) 的自動探索。
#
# 我們要的組合是：相對路徑以 infra/docker 為基準（compose 檔裡才能寫 `../../apps/api`），
# 但 `.env` 讀 repo 根目錄那一份。只有這組旗標能同時滿足兩者。
#
# 全部用 $REPO_ROOT 展開成絕對路徑，從任何 CWD 呼叫都不會壞 ——
# 相對路徑的話 --env-file 會跟著呼叫者的 CWD 跑掉。
#
# **`--env-file` 指到不存在的檔案時 compose 一定失敗**，而且不會退回讀環境變數。
# 所以每一支會呼叫這裡的腳本都要先 `require_env`（訊息會指回「先跑 make init」）——
# 少了那一步，錯誤會落在呼叫端自己的錯誤路徑上，變成跟原因無關的東西。
# 守衛不放在這個函式裡：呼叫端多半是 `$(compose config ...)`，命令替換裡的 `exit`
# 只結束子 shell，主腳本會若無其事地拿著空字串繼續跑。
compose() {
    docker compose \
        --project-directory "$COMPOSE_DIR" \
        --env-file "$REPO_ROOT/.env" \
        -f "$COMPOSE_DIR/docker-compose.yml" \
        "$@"
}

dev_compose() {
    MODE=development compose -f "$COMPOSE_DIR/docker-compose.dev.yml" "$@"
}

prod_compose() {
    MODE=production compose -f "$COMPOSE_DIR/docker-compose.prod.yml" "$@"
}

# 目前跑起來的是 dev 還是 prod，答案問正在跑的 api 容器自己。
#
# 為什麼要偵測而不是讓使用者指定：dev 與 prod 是兩組不同的 volume（見 docker-compose.yml 的
# `${COMPOSE_PROJECT_NAME}_${MODE}_postgres_data`），對錯環境跑 migration／看 logs 會指到另一份資料。
# 沒有環境在跑時回傳空字串，由呼叫端決定訊息。
detect_mode() {
    docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \
        "${COMPOSE_PROJECT_NAME}-api" 2>/dev/null | sed -n 's/^MODE=//p'
}

# 找不到運行中環境時的共用訊息。dev/prod 兩種模式都要處理的腳本用。
require_mode() {
    local mode
    mode="$(detect_mode)"
    if [ "$mode" != "development" ] && [ "$mode" != "production" ]; then
        echo "找不到運行中的 dev 或 prod 環境，請先執行 make dev 或 make prod" >&2
        exit 1
    fi
    printf '%s\n' "$mode"
}

# api 容器裡的資料庫 CLI（apps/api/scripts/db.py）。
# reset／backup／restore／create-superuser 都是它的子指令。
db_cli() {
    docker exec -w /app "${COMPOSE_PROJECT_NAME}-api" python scripts/db.py "$@"
}

# 需要互動輸入的子指令用這個（create-superuser 走 getpass，沒有 TTY 會直接失敗）。
db_cli_tty() {
    docker exec -it -w /app "${COMPOSE_PROJECT_NAME}-api" python scripts/db.py "$@"
}

# 要把資料從主機餵進 stdin 的子指令用這個（restore 的 archive）。
#
# 只有 `-i` 沒有 `-t`：加了 `-t` docker 會配一個 pseudo-TTY，把二進位串流當成終端機輸入
# 做行結尾轉換，備份檔會在中途被改幾個 byte —— pg_restore 收到的是一份壞掉的檔案。
db_cli_stdin() {
    docker exec -i -w /app "${COMPOSE_PROJECT_NAME}-api" python scripts/db.py "$@"
}
