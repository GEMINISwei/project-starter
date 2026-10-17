#!/usr/bin/env bash
#
# 目前的版本: make version
#
#   make version   印出這份 checkout 的版本 (APP_VERSION), 例如 v0.0.2
#
# 部署會 checkout 對應的 tag, 所以在部署主機上這就是正在跑的版本。回滾之後用它對照要還原
# 哪一份備份: `make db restore` 只列出、也只接受這個版本的備份。
set -euo pipefail

# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

version="$(app_version)"
echo "v${version}"
