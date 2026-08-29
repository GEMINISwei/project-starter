#!/usr/bin/env bash
#
# 執行後端 mypy 與前端 TypeScript 型別檢查。
#
# mypy 的檢查範圍在 apps/api/pyproject.toml 的 files（scripts/ 刻意不含在內）。
set -euo pipefail

# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

load_env

(cd apps/api && uv run mypy)
(cd apps/web && npm run typecheck)
