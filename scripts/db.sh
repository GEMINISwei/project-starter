#!/usr/bin/env bash
#
# 資料庫操作: make db <子指令>
#
#   make db psql                 進入資料庫 (psql)
#   make db restore [檔案]       還原這個目錄版本的備份, 還原前先完整備份一次; 不帶檔案時列出讓你選
#   make db reset                清空資料並重建結構與初始資料 (development only)
#   make db migrate              對運行中的環境套用未執行的 migration (development only)
#   make db migration "說明"     依 model 的變更產生一支 migration, 不需要啟動環境 (development only)
#   make db superuser            建立擁有全部權限的超級管理者
#   make db revoke-sessions      讓所有使用者都要重新登入 (帳號被盜、懷疑 token 外流時)
#   [內部] make db revision      印出資料庫目前的 migration revision; 全新主機什麼都不印 (部署用)
#
# 除了 migration, 都是對 `make start` 起來的那套容器操作。備份用 make backup (資料庫與上傳檔案一起)。
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
    require_env COMPOSE_PROJECT_NAME
    if ! container_running "${COMPOSE_PROJECT_NAME}-postgres"; then
        echo "資料庫沒有在執行，請先 make start" >&2
        exit 1
    fi
}

# 帳號與資料庫名稱在容器裡讀, 理由同 postgres_tool。psql 要 TTY, 而 postgres_tool 只給 -i。
# 每套系統的資料庫都叫 app, 預設提示字元 (%/ = 資料庫名稱) 分不出是哪一套, 所以換成專案名稱。
cmd_psql() {
    local prompt="${COMPOSE_PROJECT_NAME}%R%x%# "
    require_running
    # shellcheck disable=SC2016 # 刻意不在主機展開
    docker exec -it "${COMPOSE_PROJECT_NAME}-postgres" \
        sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" "$@"' sh \
        -v "PROMPT1=${prompt}" -v "PROMPT2=${prompt}"
}

# 從清單選一份這個版本的備份, 選中的路徑寫到 stdout (清單與提示走 stderr, 才能被 $() 接住)。
choose_backup() {
    local version="$1" backups=() line i
    while IFS= read -r line; do backups+=("${line}"); done < <(list_backups "${version}")
    if [ "${#backups[@]}" -eq 0 ]; then
        echo "${BACKUP_DIR}/ 裡沒有 v${version} 的備份（只列出與這個目錄版本一致的備份）" >&2
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

# 先完整備份一次再還原: 選錯檔案時還退得回來。備份失敗就不還原。
# 整段在 nginx 停著的時候做, 還原到一半時不會有請求讀寫到新舊混雜的資料。
# --clean --if-exists: 取代而不是疊加, 否則撞 duplicate key 只成功一半。
# 只用 -i 不用 -t: pseudo-TTY 會對二進位串流做換行轉換, 備份檔會在中途被改壞。
restore_database() {
    local file="$1"
    "${REPO_ROOT}/scripts/backup.sh"
    postgres_tool -i pg_restore --clean --if-exists --no-owner --no-acl < "${file}"
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
        echo "這是 v${file_version} 的備份，目前版本是 v${version}（make services 上方的版本）；先部署回 v${file_version} 再還原" >&2
        exit 1
    fi

    confirm "將先完整備份一次，再以 $(backup_label "${file}") 的備份取代目前資料庫的資料，確定？"
    without_traffic restore_database "${file}"
    echo "還原完成：$(backup_label "${file}")"
}

cmd_reset() {
    deny_on_production "make db reset"
    require_running
    confirm "資料庫的資料將被清空並重建初始資料，確定？"
    db_cli reset
    # migrate 會接著補齊初始資料 (scripts/db.py), 不必另外 seed。
    db_cli migrate
}

# 正式環境由 make start 的 migrate 服務套用; 這條路徑不會先備份。
cmd_migrate() {
    deny_on_production "make db migrate"
    require_running
    db_cli migrate
}

# 對一個拋棄式資料庫跑完既有 migration, 再讓 autogenerate 比對 model —— 不碰開發資料,
# 也不需要先啟動環境。
cmd_migration() {
    local message="$*"
    deny_on_production "make db migration"
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

# 建立超管的唯一途徑 (第一個、第二個、唯一超管失聯時的救援都是)。做成 CLI 而不是網頁上的
# 註冊碼: 後者會讓一條公開、未登入、能造出全權限帳號的端點留在網路上。
cmd_superuser() {
    require_running
    confirm "將建立一個擁有全部權限的超級管理者帳號，確定要繼續？"
    db_cli_tty create-superuser
}

# 開發機也要確認: 執行的人自己也會被登出, 而且沒有辦法復原。
cmd_revoke_sessions() {
    require_running
    confirm "所有使用者都會被登出、必須重新登入，確定？"
    db_cli revoke-sessions
}

# deploy.yml 在部署任何一套之前讀它, 判斷這次部署會不會讓資料庫往回 (scripts/lib/migrations.sh)。
# stdout 只放 revision 本身, 才能被 $() 接住。全新主機 (還沒有資料 volume) 什麼都不印。
# 有資料 volume 但資料庫沒在跑時失敗, 不當成全新主機: 那會讓回滾安靜地通過檢查。
cmd_revision() {
    local volumes
    require_env COMPOSE_PROJECT_NAME
    require_mode
    volumes="$(docker volume ls -q)" || { echo "無法列出 docker volume" >&2; exit 1; }
    grep -qx "${COMPOSE_PROJECT_NAME}_${MODE}_postgres_data" <<< "${volumes}" || return 0
    require_running
    # 資料庫建好了、但還沒跑過任何 migration 時沒有這張表。
    if [ "$(postgres_tool psql -tAq -c "SELECT to_regclass('public.alembic_version') IS NOT NULL")" = t ]; then
        postgres_tool psql -tAq -c "SELECT version_num FROM alembic_version"
    fi
}

action="${1:-}"
shift || true
case "${action}" in
    psql)      cmd_psql ;;
    restore)   cmd_restore "$@" ;;
    reset)     cmd_reset ;;
    migrate)   cmd_migrate ;;
    migration) cmd_migration "$@" ;;
    superuser) cmd_superuser ;;
    revoke-sessions) cmd_revoke_sessions ;;
    revision)  cmd_revision ;;
    *)         usage ;;
esac
