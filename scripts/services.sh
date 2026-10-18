#!/usr/bin/env bash
#
# 服務狀態與操作: make services [volumes|logs [服務]|down] (不帶參數 = 狀態)
#
#   make services              版本與 MODE、各服務的狀態 (名稱、狀態、port)、這個專案的 volume
#   make services volumes      版本與 MODE、這個專案每個 volume 的容量 (要掃過整台主機, 比較慢)
#   make services logs [服務]  追 log, 例如 make services logs api
#   make services down         停止並移除容器 (資料留在 volume; production 要先確認)
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

usage() {
    sed -n '/^#   make services/s/^#   //p' "$0" >&2
    exit 1
}

# 這個目錄的程式版本 (APP_VERSION) 與 .env 的 MODE。部署會 checkout 對應的 tag,
# 所以在主機上這就是線上的版本。
print_header() {
    echo "版本：v$(app_version)  MODE：${MODE}"
    echo
}

# 用法: print_volumes [sizes]
#
# 以 compose 加在 volume 上的專案標籤篩選 (同 make init 檢查撞名): `my-app-2` 這種開頭相同的
# 別的專案不算。名稱不是 `<專案>_<MODE>_` 開頭的標 Not Matched: 另一種模式留下的 (開發機暫時
# 切過 MODE), 或改過命名之前的舊 volume —— 目前這個 MODE 用不到, 也不會自己消失。只標不刪。
#
# 容量要 `docker system df -v`, 它會掃過整台主機的 volume, 所以只在 `make services volumes` 才查:
# 部署每次都跑 make services, 不能被它拖慢。
print_volumes() {
    local names sizes=""
    names="$(docker volume ls --filter "label=com.docker.compose.project=${COMPOSE_PROJECT_NAME}" \
        --format '{{.Name}}')" || { echo "無法列出 docker volume" >&2; exit 1; }
    echo "Volumes"
    if [ -z "${names}" ]; then
        echo "沒有 volume"
        return
    fi
    if [ "${1:-}" = sizes ]; then
        sizes="$(docker system df -v \
            --format '{{range .Volumes}}{{.Name}}{{"\t"}}{{.Size}}{{println}}{{end}}')" \
            || { echo "無法取得 volume 容量" >&2; exit 1; }
    fi
    # 值經環境變數傳進 awk, 不拼進程式: 名稱與容量不必跳脫。
    PREFIX="${COMPOSE_PROJECT_NAME}_${MODE}_" WITH_SIZES="${1:-}" SIZES="${sizes}" awk '
        BEGIN {
            n = split(ENVIRON["SIZES"], rows, "\n")
            for (i = 1; i <= n; i++) {
                split(rows[i], field, "\t")
                size[field[1]] = field[2]
            }
        }
        {
            name[NR] = $0
            value[NR] = ($0 in size) ? size[$0] : "-"
            if (length($0) > name_width) name_width = length($0)
            if (length(value[NR]) > size_width) size_width = length(value[NR])
        }
        END {
            for (i = 1; i <= NR; i++) {
                matched = index(name[i], ENVIRON["PREFIX"]) == 1
                line = name[i]
                if (ENVIRON["WITH_SIZES"] != "") {
                    line = sprintf("%-" name_width "s   %s", line, value[i])
                    if (!matched) line = sprintf("%-" (name_width + 3 + size_width) "s", line)
                } else if (!matched) {
                    line = sprintf("%-" name_width "s", line)
                }
                print matched ? line : line "   ← Not Matched"
            }
        }
    ' <<< "${names}"
}

load_env
require_env COMPOSE_PROJECT_NAME
require_mode

action="${1:-}"
shift || true
case "${action}" in
    '')
        [ "$#" -eq 0 ] || usage
        print_header
        # 預設的 ps 有 7 欄, IMAGE/COMMAND/PORTS 一長就換行; 這裡只留判斷狀態要的欄位。
        app_compose ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}'
        echo
        print_volumes
        ;;
    volumes)
        [ "$#" -eq 0 ] || usage
        print_header
        print_volumes sizes
        ;;
    # 不帶服務名稱時看全部; `make services logs api` 只看 api。
    logs) app_compose logs -f --tail=200 "$@" ;;
    down)
        [ "$#" -eq 0 ] || usage
        # 不刪 volume, 但正式環境停下來就是停機, 誤打的代價太高。
        if [ "${MODE}" = production ]; then
            confirm "將停止並移除正式環境的所有容器（資料留在 volume），確定？"
        fi
        app_compose down --remove-orphans
        ;;
    *) usage ;;
esac
