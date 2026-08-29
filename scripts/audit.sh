#!/usr/bin/env bash
#
# 掃描正式環境相依的已知漏洞（需連網，刻意不含在 check 裡）。
#
# 不掛在 check 後面的理由：它查的是外部 advisory 資料庫，會因為「今天有人公布了新漏洞」
# 而變紅 —— 那跟你這次改了什麼無關，混在原始碼檢查裡會讓人分不清是自己弄壞的還是外面變了。
set -euo pipefail

# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

load_env

(cd apps/web && npm audit --omit=dev --audit-level=high)
(cd apps/api && NO_COLOR=1 uv export --no-dev --no-emit-project --no-hashes --format requirements-txt \
    | uvx pip-audit -r /dev/stdin --progress-spinner off)
