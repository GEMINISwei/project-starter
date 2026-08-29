#!/usr/bin/env bash
#
# 由後端 OpenAPI 重新產生前端型別（不需啟動服務）。
#
# 改過任何 schema.py 或 app/permissions.py 後都要執行，CI 的 `api-types-up-to-date` job 會擋。
# 兩份產出都要一起 commit：$CONTRACT 是契約本體，$WEB_SCHEMA 是它的 TypeScript 投影。
# 細節見 contracts/README.md。
#
# 路徑一律用 $REPO_ROOT 展開成絕對路徑：下面兩行各自 cd 進不同的 app，
# 相對路徑的話同一個變數在兩行裡會指到不同地方。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

load_env

(cd apps/api && uv run python scripts/export_openapi.py "$REPO_ROOT/$CONTRACT")
(cd apps/web && npx openapi-typescript "$REPO_ROOT/$CONTRACT" -o "$REPO_ROOT/$WEB_SCHEMA")

"$SCRIPT_DIR/check-contracts.sh"
