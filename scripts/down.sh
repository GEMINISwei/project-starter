#!/usr/bin/env bash
#
# 停止並移除目前容器與網路，保留資料 volumes。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

load_env
require_env COMPOSE_PROJECT_NAME

dev_compose down --remove-orphans
