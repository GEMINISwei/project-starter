#!/usr/bin/env bash
#
# 執行後端 pytest 與前端 Vitest（帶覆蓋率）。
#
# 門檻設在 apps/api/pyproject.toml 的 fail_under 與 apps/web/vitest.config.ts 的 thresholds。
# 本機沒有 PostgreSQL 時 integration 測試會自動 skip，CI 上會真的跑。
set -euo pipefail

# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

load_env

(cd apps/api && uv run pytest tests/ -q --cov)
(cd apps/web && npm run test:coverage)
