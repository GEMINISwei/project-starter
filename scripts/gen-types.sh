#!/usr/bin/env bash
#
# 前後端型別契約: 由後端 OpenAPI 重新產生前端型別 (不需啟動服務)。
#
#   make gen-types   改過後端 schema/權限/語系後必跑 (改版號用 make release, 它會呼叫這支)
#
# 改過任何 schema.py 或 app/permissions.py 後都要執行, CI 的 `check` job 會擋。
# 兩份產出都要一起 commit: $CONTRACT 是契約本體, $WEB_SCHEMA 是它的 TypeScript 投影。
# 細節見 docs/architecture.md〈前後端契約〉。
#
# 路徑一律用 $REPO_ROOT 展開成絕對路徑: 下面兩行各自 cd 進不同的 app,
# 相對路徑的話同一個變數在兩行裡會指到不同地方。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

load_env

(cd apps/api && uv run python scripts/export_openapi.py "$REPO_ROOT/$CONTRACT")
(cd apps/web && npx openapi-typescript "$REPO_ROOT/$CONTRACT" -o "$REPO_ROOT/$WEB_SCHEMA")

test -f "$REPO_ROOT/$CONTRACT"   || { echo "找不到契約 ${CONTRACT}" >&2; exit 1; }
test -f "$REPO_ROOT/$WEB_SCHEMA" || { echo "找不到型別檔 ${WEB_SCHEMA}" >&2; exit 1; }
echo "已更新 ${CONTRACT} 與 ${WEB_SCHEMA}，兩份請一起 commit"
