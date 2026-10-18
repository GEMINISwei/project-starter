#!/usr/bin/env bash
#
# 上傳檔案 (uploads volume) 的備份與還原: make uploads <子指令>
#
#   make uploads backup           打包到 ./backups/<專案>_v<版號>_<日期>_<時間>.tar; 沒有 uploads volume 時略過
#   make uploads restore [檔案]   以備份取代目前的檔案; 不帶檔案時列出讓你選 (不限版本)
#
# 都是對 `make dev`/`make prod` 起來的那套容器操作。資料庫與上傳檔案一起備份用 make backup。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"
# shellcheck source=scripts/lib/backups.sh
source "$(dirname "$0")/lib/backups.sh"

load_env

readonly UPLOADS_DIR=/app/uploads

usage() {
    sed -n '/^#   make uploads/s/^#   //p' "$0" >&2
    exit 1
}

require_running() {
    require_env COMPOSE_PROJECT_NAME
    if ! docker ps --format '{{.Names}}' | grep -qx "${COMPOSE_PROJECT_NAME}-api"; then
        echo "api 沒有在執行，請先 make dev 或 make prod" >&2
        exit 1
    fi
}

# volume 名稱是 compose 檔裡的 `<專案>_<MODE>_uploads`。先存清單再比對, 理由同 db.sh 的 is_fresh_host。
has_uploads_volume() {
    require_env COMPOSE_PROJECT_NAME
    local volumes
    volumes="$(docker volume ls -q)" || { echo "無法列出 docker volume" >&2; exit 1; }
    grep -qxE "${COMPOSE_PROJECT_NAME}_(production|development)_uploads" <<< "${volumes}"
}

# 從 api 容器裡打包, 不另起容器: 主機上不必多拉一個 image, 也跟 make db 一樣只要求服務在跑。
# 不壓縮: 圖片、影片本身已經壓過, 再 gzip 省不到空間只花 CPU。
# volume 不存在時 (全新主機, 或還沒部署過有 uploads 的版本) 沒有東西可備份, 略過。
cmd_backup() {
    if ! has_uploads_volume; then
        echo "沒有 uploads volume，略過上傳檔案的備份"
        return 0
    fi
    require_running
    mkdir -p "${BACKUP_DIR}"
    local dest
    # BACKUP_TIME 由 make backup 給, 理由見 db.sh 的 cmd_backup。
    dest="$(backup_name "${COMPOSE_PROJECT_NAME}" "$(app_version)" "${BACKUP_TIME:-$(date +%Y%m%d_%H%M%S)}" tar)"
    docker exec "${COMPOSE_PROJECT_NAME}-api" tar -C "${UPLOADS_DIR}" -cf - . > "${dest}.partial"
    mv "${dest}.partial" "${dest}"
    echo "已備份：${dest}"
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

# 不檢查版號: 檔案沒有結構, 哪一版的備份都能還原。
# 先清空再解開: 疊加的話備份之後才上傳的檔案會留下, 變成資料庫裡沒有紀錄的孤兒。
# 只用 -i 不用 -t, 理由同 db.sh 的 cmd_restore。
cmd_restore() {
    require_running
    local file="${1:-}"
    if [ -z "${file}" ]; then
        file="$(choose_backup)"
    fi
    [ -f "${file}" ] || { echo "找不到檔案：${file}" >&2; exit 1; }
    local label
    label="$(backup_label "${file}" || basename "${file}")"
    confirm "將以 ${label} 的備份取代目前所有上傳的檔案，確定？"
    docker exec -i "${COMPOSE_PROJECT_NAME}-api" sh -c \
        'find "$1" -mindepth 1 -delete && tar -C "$1" -xf -' _ "${UPLOADS_DIR}" < "${file}"
    echo "還原完成：${label}"
}

action="${1:-}"
shift || true
case "${action}" in
    backup)  cmd_backup ;;
    restore) cmd_restore "$@" ;;
    *)       usage ;;
esac
