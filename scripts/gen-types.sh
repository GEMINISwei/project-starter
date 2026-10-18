#!/usr/bin/env bash
#
# 前後端型別契約: 由後端 OpenAPI 重新產生前端型別 (不需啟動服務)。
#
#   make gen-types   改過後端 schema/權限/語系後必跑
#
# 這是唯一會把契約寫進 repo 的指令。`make check` 與 `make release` 只比對, 不一致就擋
# (scripts/lib/contract.sh)。兩份產出都要一起 commit: $CONTRACT 是契約本體,
# $WEB_SCHEMA 是它的 TypeScript 投影。細節見 docs/architecture.md〈前後端契約〉。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib/contract.sh
source "$SCRIPT_DIR/lib/contract.sh"

load_env

generate_contract "$REPO_ROOT/$CONTRACT" "$REPO_ROOT/$WEB_SCHEMA"

test -f "$REPO_ROOT/$CONTRACT"   || { echo "找不到契約 ${CONTRACT}" >&2; exit 1; }
test -f "$REPO_ROOT/$WEB_SCHEMA" || { echo "找不到型別檔 ${WEB_SCHEMA}" >&2; exit 1; }
echo "已更新 ${CONTRACT} 與 ${WEB_SCHEMA}，兩份請一起 commit"
