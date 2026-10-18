#!/usr/bin/env bash
#
# 一次備份資料庫與上傳檔案: make backup <子指令>
#
#   make backup                  同一個時間點產出 <名稱>.dump 與 <名稱>.tar (沒有 uploads volume 時只有 .dump)
#   make backup allow-fresh      同上, 但全新主機 (還沒有資料 volume) 時略過 (部署用)
#   make backup prune <組數>     只留最近幾組備份, 同名的 .dump 與 .tar 一起刪
#
# 只備份其中一邊用 make db backup／make uploads backup; 還原一律分開 (make db restore／make uploads restore)。
set -euo pipefail

# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"
# shellcheck source=scripts/lib/backups.sh
source "$(dirname "$0")/lib/backups.sh"

usage() {
    sed -n '/^#   make backup/s/^#   //p' "$0" >&2
    exit 1
}

# 兩邊共用同一個時間, 檔名只差副檔名, 看得出是同一組。
# 先資料庫再檔案: 資料庫失敗時 (主機狀態不對) 就停, 不留下只有檔案的半組。
cmd_backup() {
    local mode="${1:-}"
    case "${mode}" in
        ''|allow-fresh) ;;
        *) usage ;;
    esac
    BACKUP_TIME="$(date +%Y%m%d_%H%M%S)"
    export BACKUP_TIME
    "${REPO_ROOT}/scripts/db.sh" backup ${mode:+"${mode}"}
    "${REPO_ROOT}/scripts/uploads.sh" backup
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
