#!/usr/bin/env bash
#
# 正式環境: make prod [up|down|logs [服務]|ps] (不帶參數 = 重新建置 image 並啟動)
#
#   make prod              重新建置 image 並啟動 (會自動跑 migration)
#   make prod down         停止並移除容器 (資料留在 volume)
#   make prod logs [服務]  追 log
#   make prod ps           看各服務狀態
#
# shell 有匯出 API_IMAGE 與 WEB_IMAGE 時, `make prod` 改成從 registry 拉這兩個 image,
# 不在主機上建置 (deploy workflow 走這條, 見 docs/operations.md〈自動部署〉)。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

stack prod "$@"
