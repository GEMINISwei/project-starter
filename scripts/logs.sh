#!/usr/bin/env bash
#
# 依目前運行模式選擇服務並查看 logs。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

load_env
require_env COMPOSE_PROJECT_NAME

mode="$(require_mode)"

case "$mode" in
    development) services="$(dev_compose config --services)" ;;
    production)  services="$(prod_compose config --services)" ;;
esac

echo "可用服務："
printf '%s\n' "$services" | sed 's/^/  /'
printf '請輸入服務名稱（留空顯示全部）：'
read -r service

# $service 刻意不加引號：留空時要展開成「零個參數」（等於看全部服務），
# 加引號會變成傳一個空字串參數，compose 會抱怨找不到叫 "" 的服務。
# shellcheck disable=SC2086 # 上面那段就是不加引號的理由
case "$mode" in
    development) dev_compose logs -f $service ;;
    production)  prod_compose logs -f $service ;;
esac
