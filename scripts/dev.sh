#!/usr/bin/env bash
#
# 開發環境: make dev [up|down|logs [服務]|ps [full]] (不帶參數 = up)
#
#   make dev              啟動 (postgres → migrate → api → web → nginx, 會自動跑 migration)
#   make dev down         停止並移除容器 (資料留在 volume)
#   make dev logs [服務]  追 log, 例如 make dev logs api
#   make dev ps           看各服務狀態 (名稱、狀態、port)
#   make dev ps full      完整的 docker compose ps
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

stack dev "$@"
