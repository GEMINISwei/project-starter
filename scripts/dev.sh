#!/usr/bin/env bash
#
# 以 development 模式啟動開發環境。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

load_env
require_env COMPOSE_PROJECT_NAME

dev_compose up -d --remove-orphans
