#!/usr/bin/env bash
#
# 執行前端 production build。
#
# load_env 是必要的，不只是順手：next.config.ts 在載入時會讀 UPLOAD_SIZE_LIMIT 之類的
# 環境變數並驗證格式。Makefile 不 export 任何東西，這些值只能由這裡載進來 ——
# 少了它，build 產出會跟預期悄悄不一樣。
set -euo pipefail

# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

load_env

(cd apps/web && npm run build)
