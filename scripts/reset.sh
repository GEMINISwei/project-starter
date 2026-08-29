#!/usr/bin/env bash
#
# 清空並重建初始資料，僅限開發環境使用。
#
# 在 api 容器內執行，需先 make dev 或 make prod 啟動環境。
# db.py 本身會拒絕在 MODE != development 時執行 reset，這裡不重複那道防線。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

load_env
require_env COMPOSE_PROJECT_NAME

confirm "現有資料將被清除並重建初始資料，確定要重置資料庫？"

db_cli reset
db_cli seed
