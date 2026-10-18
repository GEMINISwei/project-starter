#!/usr/bin/env bash
#
# 備份檔的命名、挑選與清理: `make backup` 產生, `make db restore`／`make uploads restore` 挑選。
#
#   backups/<專案>_v<版號>_<日期>_<時間>.dump   資料庫, 例如 backups/my-app_v0.0.1_20261017_083553.dump
#   backups/<專案>_v<版號>_<日期>_<時間>.tar    上傳檔案 (uploads volume)
#
# 兩份只差副檔名, 同一個主幹就是同一組, 清理時一起刪。
#
# 版號是備份當下這份 checkout 的版本, 也就是資料表結構所屬的版本: 回滾到某一版之後只能還原
# 那一版的備份 (新版 migration 改過的結構, 舊程式讀不了), 所以 restore 只認版號一致的檔案。
#
# 這支是被 source 的, 所以刻意**不**寫 `set -euo pipefail` (同 common.sh)。
# 也不 source common.sh: 那支會 cd 到 repo 根, 測試要在別的目錄跑這些函式。

[ -n "${BACKUPS_SH_LOADED:-}" ] && return 0
BACKUPS_SH_LOADED=1

readonly BACKUP_DIR=backups
# shellcheck disable=SC2034 # 給 source 這支的腳本用 (backup.sh、uploads.sh)
# uploads volume 在 api 容器裡的掛載點 (compose 檔), 備份與還原都從這裡打包、解開。
readonly UPLOADS_DIR=/app/uploads
# 從檔名尾端比對: 專案名稱本身可以有底線或 `_v`。
readonly BACKUP_PATTERN='_v([0-9]+\.[0-9]+\.[0-9]+)_([0-9]{8})_([0-9]{6})\.(dump|tar)$'

# 用法: backup_name <專案> <版號> <YYYYmmdd_HHMMSS> [副檔名, 預設 dump]
backup_name() {
    printf '%s/%s_v%s_%s.%s\n' "${BACKUP_DIR}" "$1" "$2" "$3" "${4:-dump}"
}

# 印出備份檔的版號 (不帶 v)。檔名不符合命名時 (例如改版前的舊備份) 回傳 1。
backup_version() {
    [[ "$(basename "$1")" =~ ${BACKUP_PATTERN} ]] || return 1
    printf '%s\n' "${BASH_REMATCH[1]}"
}

# 給確認的人看的一行, 不帶路徑: `v0.0.1 2026-10-17 08:35:53`
backup_label() {
    [[ "$(basename "$1")" =~ ${BACKUP_PATTERN} ]] || return 1
    local version="${BASH_REMATCH[1]}" day="${BASH_REMATCH[2]}" time="${BASH_REMATCH[3]}"
    printf 'v%s %s-%s-%s %s:%s:%s\n' "${version}" \
        "${day:0:4}" "${day:4:2}" "${day:6:2}" "${time:0:2}" "${time:2:2}" "${time:4:2}"
}

# 用法: list_backups <版號>
#
# 列出這個版號的備份, 新到舊。依檔名裡的時間排序而不是 mtime: 複製或搬過主機的檔案 mtime 會變。
list_backups() {
    local file
    for file in "${BACKUP_DIR}"/*.dump; do
        [ -f "${file}" ] || continue
        if [[ "$(basename "${file}")" =~ ${BACKUP_PATTERN} ]] && [ "${BASH_REMATCH[1]}" = "$1" ]; then
            printf '%s%s\t%s\n' "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" "${file}"
        fi
    done | sort -r | cut -f2-
}

# 列出所有版本的上傳檔案備份, 新到舊。不篩版號: 檔案沒有結構, 哪一版的都能還原。
list_uploads_backups() {
    local file
    for file in "${BACKUP_DIR}"/*.tar; do
        [ -f "${file}" ] || continue
        if [[ "$(basename "${file}")" =~ ${BACKUP_PATTERN} ]]; then
            printf '%s%s\t%s\n' "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" "${file}"
        fi
    done | sort -r | cut -f2-
}

# 用法: backups_to_prune <保留組數>
#
# 印出最近 N 組以外的備份檔。以檔名主幹為一組 (`.dump` 與 `.tar` 一起算), 不分版號;
# 依檔名的時間排序, 理由同 list_backups。不符合命名的檔案 (.partial、舊命名) 一律不碰。
# 組數必須是正整數: 0 會刪光全部備份。
backups_to_prune() {
    if ! [[ "${1:-}" =~ ^[1-9][0-9]*$ ]]; then
        echo "保留組數必須是正整數：「${1:-}」" >&2
        return 1
    fi
    local keep="$1" file stem
    local -a stems=()
    while IFS= read -r stem; do stems+=("${stem}"); done < <(
        for file in "${BACKUP_DIR}"/*; do
            [ -f "${file}" ] || continue
            if [[ "$(basename "${file}")" =~ ${BACKUP_PATTERN} ]]; then
                printf '%s%s\t%s\n' "${BASH_REMATCH[2]}" "${BASH_REMATCH[3]}" "${file%.*}"
            fi
        done | sort -ru | cut -f2- | tail -n +"$((keep + 1))"
    )
    for stem in ${stems[@]+"${stems[@]}"}; do
        for file in "${stem}.dump" "${stem}.tar"; do
            [ -f "${file}" ] && printf '%s\n' "${file}"
        done
    done
    return 0
}
