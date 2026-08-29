#!/usr/bin/env bash
#
# 執行尚未套用的 migration（見 apps/api/scripts/migrations/）。
#
# 部署時不需手動執行：compose 的 migrate service 會在 api 啟動前自動跑完。
# 這支是給「開發中新增了一支 migration，想立刻套用」用的。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

load_env
require_env COMPOSE_PROJECT_NAME

mode="$(require_mode)"

case "$mode" in
    development) dev_compose  run --rm migrate ;;
    production)  prod_compose run --rm migrate ;;
esac
