#!/usr/bin/env bash
#
# 資料庫操作: make db <子指令>
#
#   make db psql                 進入資料庫 (psql)
#   make db backup               備份到 ./backups/<資料庫>_<時間>.dump
#   make db restore [檔案]       還原; 不帶檔案時列出 ./backups/ 讓你選
#   make db reset                清空資料並重建結構與初始資料 (dev only)
#   make db migrate              對運行中的環境套用未執行的 migration
#   make db migration "說明"     依 model 的變更產生一支 migration (不需要啟動環境)
#   make db superuser            建立擁有全部權限的超級管理者
#
# 除了 migration, 都是對 `make dev`/`make prod` 起來的那套容器操作。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"
# shellcheck source=scripts/lib/pg.sh
source "$(dirname "$0")/lib/pg.sh"

load_env

usage() {
    sed -n '/^#   make db/s/^#   //p' "$0" >&2
    exit 1
}

# 碰運行中容器的子指令都要先確認環境起著, 否則 docker 的錯誤訊息看不出原因。
require_running() {
    require_env COMPOSE_PROJECT_NAME POSTGRES_USER POSTGRES_DB
    if ! docker ps --format '{{.Names}}' | grep -qx "${COMPOSE_PROJECT_NAME}-postgres"; then
        echo "資料庫沒有在執行，請先 make dev 或 make prod" >&2
        exit 1
    fi
}

cmd_psql() {
    require_running
    docker exec -it -e PGPASSWORD="${POSTGRES_PASSWORD:-}" "${COMPOSE_PROJECT_NAME}-postgres" \
        psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"
}

# custom 格式 (-Fc) 本身有壓縮, 還原時 pg_restore 能自己處理外鍵順序。
# 先寫到暫存檔再改名: 中途失敗時 backups/ 裡不會留下一份看起來完整的壞檔。
cmd_backup() {
    require_running
    mkdir -p backups
    local dest
    dest="backups/${POSTGRES_DB}_$(date +%Y%m%d_%H%M%S).dump"
    docker exec -e PGPASSWORD="${POSTGRES_PASSWORD:-}" "${COMPOSE_PROJECT_NAME}-postgres" \
        pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc --no-owner --no-acl > "${dest}.partial"
    mv "${dest}.partial" "${dest}"
    echo "已備份：${dest}"
}

cmd_restore() {
    require_running
    local file="${1:-}"
    if [ -z "${file}" ]; then
        local backups=()
        while IFS= read -r line; do backups+=("${line}"); done < <(ls -1t backups/*.dump 2>/dev/null)
        if [ "${#backups[@]}" -eq 0 ]; then
            echo "backups/ 裡沒有備份，請先 make db backup" >&2
            exit 1
        fi
        echo "可用的備份（新到舊）："
        local i
        for i in "${!backups[@]}"; do printf '  %d) %s\n' "$((i + 1))" "${backups[$i]}"; done
        printf '選擇編號：'
        read -r i
        file="${backups[$((i - 1))]:-}"
        [ -n "${file}" ] || { echo "無效的編號" >&2; exit 1; }
    fi
    [ -f "${file}" ] || { echo "找不到檔案：${file}" >&2; exit 1; }

    confirm "將以 ${file} 取代 ${POSTGRES_DB} 目前的資料，確定？"
    # --clean --if-exists: 取代而不是疊加, 否則撞 duplicate key 只成功一半。
    # 只用 -i 不用 -t: pseudo-TTY 會對二進位串流做換行轉換, 備份檔會在中途被改壞。
    docker exec -i -e PGPASSWORD="${POSTGRES_PASSWORD:-}" "${COMPOSE_PROJECT_NAME}-postgres" \
        pg_restore -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists --no-owner --no-acl \
        < "${file}"
    echo "還原完成：${file}"
}

cmd_reset() {
    require_running
    confirm "${POSTGRES_DB} 的資料將被清空並重建初始資料，確定？"
    db_cli reset
    db_cli migrate
    db_cli seed
}

cmd_migrate() {
    require_running
    db_cli migrate
}

# 對一個拋棄式資料庫跑完既有 migration, 再讓 autogenerate 比對 model —— 不碰開發資料,
# 也不需要先啟動環境。
cmd_migration() {
    local message="$*"
    [ -n "${message}" ] || { echo "用法：make db migration \"這支 migration 在做什麼\"" >&2; exit 1; }

    local container="${COMPOSE_PROJECT_NAME:-project-starter}-migration-gen"
    require_docker
    start_throwaway_postgres "${container}"
    trap 'docker rm -f "'"${container}"'" > /dev/null 2>&1 || true' EXIT

    cd apps/api
    POSTGRES_URL="${THROWAWAY_PG_URL}" uv run alembic upgrade head > /dev/null
    POSTGRES_URL="${THROWAWAY_PG_URL}" uv run alembic revision --autogenerate -m "${message}"

    echo
    echo "產生完成。**請自己讀一遍那個檔案**，autogenerate 固定會漏三件事："
    echo "  - 資料：往有資料的表加 NOT NULL 欄位，它只寫 ADD COLUMN，不會回填"
    echo "  - 改名：欄位或表改名會被看成 drop 一個、add 一個，照著跑資料就沒了"
    echo "  - 不能在交易裡跑的 DDL（CREATE INDEX CONCURRENTLY）"
}

# 用於唯一超管失聯、或需要多個超管時。做成 CLI 而不是再發一組註冊碼: 後者會讓一條公開、
# 未登入、能造出全權限帳號的端點長期留在網路上。
cmd_superuser() {
    require_running
    confirm "將建立一個擁有全部權限的超級管理者帳號，確定要繼續？"
    db_cli_tty create-superuser
}

action="${1:-}"
shift || true
case "${action}" in
    psql)      cmd_psql ;;
    backup)    cmd_backup ;;
    restore)   cmd_restore "$@" ;;
    reset)     cmd_reset ;;
    migrate)   cmd_migrate ;;
    migration) cmd_migration "$@" ;;
    superuser) cmd_superuser ;;
    *)         usage ;;
esac
