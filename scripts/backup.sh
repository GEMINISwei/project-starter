#!/usr/bin/env bash
#
# 備份資料庫與上傳檔案: make backup (備份期間對外服務會暫停)
#
#   make backup                          同一個時間點產出 <名稱>.dump 與 <名稱>.tar (沒有 uploads volume 時只有 .dump)
#   [內部] make backup allow-fresh       同上, 但全新主機 (還沒有資料 volume) 時略過 (部署用)
#   [內部] make backup prune <組數>      只留最近幾組備份, 同名的 .dump 與 .tar 一起刪 (部署用)
#
# 這是唯一的備份入口, 沒有只備份一邊的指令: 單邊的備份配不成一組, 還原時容易選錯。
# 還原一律分開 (make db restore／make uploads restore), 兩者都會先跑一次這支。
#
# 備份期間停掉 nginx (without_traffic): 沒有新的寫入, 資料庫與上傳檔案才是同一個時間點。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"
# shellcheck source=scripts/lib/backups.sh
source "$(dirname "$0")/lib/backups.sh"

usage() {
    sed -n '/^#   make backup/s/^#   //p' "$0" >&2
    exit 1
}

# 資料 volume 的名稱是 compose 檔裡的 `<專案>_<MODE>_postgres_data`, MODE 取自 .env。
#
# 先把清單存下來再比對, 不直接接 `| grep -q`: grep 提早結束會讓 docker 收到 SIGPIPE, 在 pipefail
# 下整條管線算失敗, 經過 `!` 就變成「全新主機」—— 有資料的主機會安靜地略過備份。
# docker 本身失敗要明確 exit: 這個函式在 `if` 條件裡被呼叫, 那裡 `set -e` 不生效, 不攔的話
# 空清單同樣會被當成全新主機。
is_fresh_host() {
    local volumes
    volumes="$(docker volume ls -q)" || { echo "無法列出 docker volume" >&2; exit 1; }
    ! grep -qx "${COMPOSE_PROJECT_NAME}_${MODE}_postgres_data" <<< "${volumes}"
}

# volume 名稱是 compose 檔裡的 `<專案>_<MODE>_uploads`。先存清單再比對, 理由同 is_fresh_host。
has_uploads_volume() {
    local volumes
    volumes="$(docker volume ls -q)" || { echo "無法列出 docker volume" >&2; exit 1; }
    grep -qx "${COMPOSE_PROJECT_NAME}_${MODE}_uploads" <<< "${volumes}"
}

# 碰運行中容器之前先確認, 否則 docker 的錯誤訊息看不出原因。
require_container() {
    if ! container_running "$1"; then
        echo "$1 沒有在執行，請先 make start" >&2
        exit 1
    fi
}

# custom 格式 (-Fc) 本身有壓縮, 還原時 pg_restore 能自己處理外鍵順序。
# 先寫到暫存檔再改名: 中途失敗時 backups/ 裡不會留下一份看起來完整的壞檔。
backup_database() {
    local dest="$1.dump"
    postgres_tool pg_dump -Fc --no-owner --no-acl > "${dest}.partial"
    mv "${dest}.partial" "${dest}"
    echo "已備份：${dest}"
}

# 從 api 容器裡打包, 不另起容器: 主機上不必多拉一個 image。所以停服務只停 nginx, api 要留著。
# 不壓縮: 圖片、影片本身已經壓過, 再 gzip 省不到空間只花 CPU。
# volume 不存在時 (還沒部署過有 uploads 的版本) 沒有東西可備份, 略過。
backup_uploads() {
    local dest="$1.tar"
    if ! has_uploads_volume; then
        echo "沒有 uploads volume，略過上傳檔案的備份"
        return 0
    fi
    require_container "${COMPOSE_PROJECT_NAME}-api"
    docker exec "${COMPOSE_PROJECT_NAME}-api" tar -C "${UPLOADS_DIR}" -cf - . > "${dest}.partial"
    mv "${dest}.partial" "${dest}"
    echo "已備份：${dest}"
}

# 兩份共用同一個檔名主幹, 只差副檔名, 看得出是同一組。
# 先資料庫再檔案: 資料庫失敗時 (主機狀態不對) 就停, 不留下只有檔案的半組。
backup_both() {
    local stem
    stem="$(backup_name "${COMPOSE_PROJECT_NAME}" "$(app_version)" "$(date +%Y%m%d_%H%M%S)")"
    stem="${stem%.dump}"
    backup_database "${stem}"
    backup_uploads "${stem}"
}

# allow-fresh 給 deploy.yml 用, 讓第一次部署不必先在主機上把服務跑起來。只放行「資料 volume
# 根本不存在」: volume 在但資料庫沒在跑, 代表主機狀態不是預期的, 照樣中止, 留給人先看過。
cmd_backup() {
    local mode="${1:-}"
    case "${mode}" in
        ''|allow-fresh) ;;
        *) usage ;;
    esac
    load_env
    require_env COMPOSE_PROJECT_NAME
    require_mode
    if [ "${mode}" = allow-fresh ] && is_fresh_host; then
        echo "還沒有任何資料（第一次部署），略過備份"
        return 0
    fi
    require_container "${COMPOSE_PROJECT_NAME}-postgres"
    mkdir -p "${BACKUP_DIR}"
    without_traffic backup_both
}

cmd_prune() {
    [ "$#" -eq 1 ] || usage
    local listing file count=0
    # 先整份接住再刪: 組數不合法時要在這裡中止, 不能只是讀到空清單。
    listing="$(backups_to_prune "$1")" || exit 1
    while IFS= read -r file; do
        [ -n "${file}" ] || continue
        rm -f "${file}"
        count=$((count + 1))
    done <<< "${listing}"
    echo "保留最近 $1 組，刪除 ${count} 個檔案"
}

action="${1:-}"
shift || true
case "${action}" in
    '')          cmd_backup ;;
    allow-fresh) cmd_backup allow-fresh ;;
    prune)       cmd_prune "$@" ;;
    *)           usage ;;
esac
