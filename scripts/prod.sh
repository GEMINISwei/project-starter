#!/usr/bin/env bash
#
# 以 production 模式重新建置 image 並啟動服務。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

load_env
require_env COMPOSE_PROJECT_NAME

prod_compose up -d --build --remove-orphans
