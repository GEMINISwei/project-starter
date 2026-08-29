#!/usr/bin/env bash
#
# 執行後端 Ruff 與前端 ESLint。
#
# 在主機上跑，不是在容器裡 —— 那才是編輯器與 CI 看到的環境。首次執行前先跑 make setup。
# 前端的 npm run lint 會連帶跑三支自訂檢查器：check:architecture（依賴邊界與模組檔案放置）、
# check:tokens（設計 token 與 CSS）、check:deadcode（未使用的匯出）。
set -euo pipefail

# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

load_env

(cd apps/api && uv run ruff check .)
(cd apps/web && npm run lint)
