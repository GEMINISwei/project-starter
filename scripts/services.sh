#!/usr/bin/env bash
#
# 服務狀態與操作: make services [logs [服務]|down] (不帶參數 = 狀態)
#
#   make services              各服務的狀態 (名稱、狀態、port), 上方附這個目錄的版本
#   make services logs [服務]  追 log, 例如 make services logs api
#   make services down         停止並移除容器 (資料留在 volume; production 要先確認)
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

usage() {
    sed -n '/^#   make services/s/^#   //p' "$0" >&2
    exit 1
}

load_env
require_env COMPOSE_PROJECT_NAME
require_mode

action="${1:-}"
shift || true
case "${action}" in
    '')
        [ "$#" -eq 0 ] || usage
        # 這個目錄的程式版本 (APP_VERSION)。部署會 checkout 對應的 tag, 所以在主機上就是線上的版本。
        echo "版本：v$(app_version)"
        # 預設的 ps 有 7 欄, IMAGE/COMMAND/PORTS 一長就換行; 這裡只留判斷狀態要的欄位。
        app_compose ps --format 'table {{.Name}}\t{{.Status}}\t{{.Ports}}'
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
