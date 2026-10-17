#!/usr/bin/env bash
#
# 資料庫操作: make db <子指令>
#
#   make db psql                 進入資料庫 (psql)
#   make db backup               備份到 ./backups/<專案>_v<版號>_<日期>_<時間>.dump
#   make db backup allow-fresh   同上, 但全新主機 (還沒有資料 volume) 時略過 (部署用)
#   make db restore [檔案]       還原目前版本 (make version) 的備份; 不帶檔案時列出讓你選
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
# shellcheck source=scripts/lib/backups.sh
source "$(dirname "$0")/lib/backups.sh"

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

# 資料 volume 的名稱是 compose 檔裡的 `<專案>_<MODE>_postgres_data`; dev 與 prod 都算,
# 一台主機只跑一種模式, 哪一種有資料都不是全新主機。
#
# 先把清單存下來再比對, 不直接接 `| grep -q`: grep 提早結束會讓 docker 收到 SIGPIPE, 在 pipefail
# 下整條管線算失敗, 經過 `!` 就變成「全新主機」—— 有資料的主機會安靜地略過備份。
# docker 本身失敗要明確 exit: 這個函式在 `if` 條件裡被呼叫, 那裡 `set -e` 不生效, 不攔的話
# 空清單同樣會被當成全新主機。
is_fresh_host() {
    require_env COMPOSE_PROJECT_NAME
    local volumes
    volumes="$(docker volume ls -q)" || { echo "無法列出 docker volume" >&2; exit 1; }
    ! grep -qxE "${COMPOSE_PROJECT_NAME}_(production|development)_postgres_data" <<< "${volumes}"
}

# custom 格式 (-Fc) 本身有壓縮, 還原時 pg_restore 能自己處理外鍵順序。
# 先寫到暫存檔再改名: 中途失敗時 backups/ 裡不會留下一份看起來完整的壞檔。
#
# allow-fresh 給 deploy.yml 用, 讓第一次部署不必先在主機上把服務跑起來。只放行「資料 volume
# 根本不存在」: volume 在但資料庫沒在跑, 代表主機狀態不是預期的, 照樣中止, 留給人先看過。
cmd_backup() {
    local mode="${1:-}"
    case "${mode}" in
        ''|allow-fresh) ;;
        *) usage ;;
    esac
    if [ "${mode}" = allow-fresh ] && is_fresh_host; then
        echo "還沒有任何資料（第一次部署），略過備份"
        return 0
    fi
    require_running
    mkdir -p "${BACKUP_DIR}"
    local version dest
    version="$(app_version)"
    dest="$(backup_name "${COMPOSE_PROJECT_NAME}" "${version}" "$(date +%Y%m%d_%H%M%S)")"
    docker exec -e PGPASSWORD="${POSTGRES_PASSWORD:-}" "${COMPOSE_PROJECT_NAME}-postgres" \
        pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -Fc --no-owner --no-acl > "${dest}.partial"
    mv "${dest}.partial" "${dest}"
    echo "已備份：${dest}"
}

# 從清單選一份這個版本的備份, 選中的路徑寫到 stdout (清單與提示走 stderr, 才能被 $() 接住)。
choose_backup() {
    local version="$1" backups=() line i
    while IFS= read -r line; do backups+=("${line}"); done < <(list_backups "${version}")
    if [ "${#backups[@]}" -eq 0 ]; then
        echo "${BACKUP_DIR}/ 裡沒有 v${version} 的備份（只列出與 make version 一致的版本）" >&2
        exit 1
    fi
    echo "v${version} 的備份（新到舊）：" >&2
    for i in "${!backups[@]}"; do
        printf '  %d) %s\n' "$((i + 1))" "$(backup_label "${backups[$i]}")" >&2
    done
    printf '選擇編號：' >&2
    read -r i
    # 先擋非數字與 0: 陣列索引是算術運算, `0` 會變成 -1 選到最舊的那份。
    if ! [[ "${i}" =~ ^[1-9][0-9]*$ ]] || [ "${i}" -gt "${#backups[@]}" ]; then
        echo "無效的編號" >&2
        exit 1
    fi
    printf '%s\n' "${backups[$((i - 1))]}"
}

# 只接受目前版本的備份: 回滾後的舊程式讀不了新版 migration 改過的結構,
# 要還原別版的備份就先部署回那一版。
cmd_restore() {
    require_running
    local version file="${1:-}" file_version
    version="$(app_version)"
    if [ -z "${file}" ]; then
        file="$(choose_backup "${version}")"
    fi
    [ -f "${file}" ] || { echo "找不到檔案：${file}" >&2; exit 1; }
    if ! file_version="$(backup_version "${file}")"; then
        echo "無法從檔名判斷 ${file} 的版本（應為 <專案>_v<版號>_<日期>_<時間>.dump）" >&2
        exit 1
    fi
    if [ "${file_version}" != "${version}" ]; then
        echo "這是 v${file_version} 的備份，目前版本是 v${version}（make version）；先部署回 v${file_version} 再還原" >&2
        exit 1
    fi

    confirm "將以 $(backup_label "${file}") 的備份取代 ${POSTGRES_DB} 目前的資料，確定？"
    # --clean --if-exists: 取代而不是疊加, 否則撞 duplicate key 只成功一半。
    # 只用 -i 不用 -t: pseudo-TTY 會對二進位串流做換行轉換, 備份檔會在中途被改壞。
    docker exec -i -e PGPASSWORD="${POSTGRES_PASSWORD:-}" "${COMPOSE_PROJECT_NAME}-postgres" \
        pg_restore -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists --no-owner --no-acl \
        < "${file}"
    echo "還原完成：$(backup_label "${file}")"
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

    require_env COMPOSE_PROJECT_NAME
    local container="${COMPOSE_PROJECT_NAME}-migration-gen"
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
    backup)    cmd_backup "$@" ;;
    restore)   cmd_restore "$@" ;;
    reset)     cmd_reset ;;
    migrate)   cmd_migrate ;;
    migration) cmd_migration "$@" ;;
    superuser) cmd_superuser ;;
    *)         usage ;;
esac
