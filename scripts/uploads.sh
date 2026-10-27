#!/usr/bin/env bash
#
# 上傳檔案 (uploads volume) 的還原: make uploads <子指令>
#
#   make uploads restore [檔案]   以備份取代目前的檔案, 還原前先完整備份一次; 不帶檔案時列出讓你選 (不限版本)
#
# 對 `make start` 起來的那套容器操作。備份用 make backup (資料庫與上傳檔案一起)。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"
# shellcheck source=scripts/lib/backups.sh
source "$(dirname "$0")/lib/backups.sh"

load_env

usage() {
    sed -n '/^#   make uploads/s/^#   //p' "$0" >&2
    exit 1
}

require_running() {
    require_env COMPOSE_PROJECT_NAME
    if ! container_running "${COMPOSE_PROJECT_NAME}-api"; then
        echo "api 沒有在執行，請先 make start" >&2
        exit 1
    fi
}

choose_backup() {
    local backups=() line i
    while IFS= read -r line; do backups+=("${line}"); done < <(list_uploads_backups)
    if [ "${#backups[@]}" -eq 0 ]; then
        echo "${BACKUP_DIR}/ 裡沒有上傳檔案的備份" >&2
        exit 1
    fi
    echo "上傳檔案的備份（新到舊）：" >&2
    for i in "${!backups[@]}"; do
        printf '  %d) %s\n' "$((i + 1))" "$(backup_label "${backups[$i]}")" >&2
    done
    printf '選擇編號：' >&2
    read -r i
    # 先擋非數字與 0, 理由同 db.sh。
    if ! [[ "${i}" =~ ^[1-9][0-9]*$ ]] || [ "${i}" -gt "${#backups[@]}" ]; then
        echo "無效的編號" >&2
        exit 1
    fi
    printf '%s\n' "${backups[$((i - 1))]}"
}

# 先完整備份一次再還原, 整段在 nginx 停著的時候做, 理由同 db.sh 的 restore_database。
# 先清空再解開: 疊加的話備份之後才上傳的檔案會留下, 變成資料庫裡沒有紀錄的孤兒。
# 只用 -i 不用 -t, 理由同 db.sh。
restore_uploads() {
    local file="$1"
    "${REPO_ROOT}/scripts/backup.sh"
    docker exec -i "${COMPOSE_PROJECT_NAME}-api" sh -c \
        'find "$1" -mindepth 1 -delete && tar -C "$1" -xf -' _ "${UPLOADS_DIR}" < "${file}"
}

# 不檢查版號: 檔案沒有結構, 哪一版的備份都能還原。
cmd_restore() {
    require_running
    local file="${1:-}"
    if [ -z "${file}" ]; then
        file="$(choose_backup)"
    fi
    [ -f "${file}" ] || { echo "找不到檔案：${file}" >&2; exit 1; }
    local label
    label="$(backup_label "${file}" || basename "${file}")"
    confirm "將先完整備份一次，再以 ${label} 的備份取代目前所有上傳的檔案，確定？"
    without_traffic restore_uploads "${file}"
    echo "還原完成：${label}"
}

action="${1:-}"
shift || true
case "${action}" in
    restore) cmd_restore "$@" ;;
    *)       usage ;;
esac
