#!/usr/bin/env bash
#
# 互動式建立額外的超級管理者（需在終端機執行）。
#
# 網頁 /signup 整個部署只能成功一次，之後只能用這個指令新增。
# 密碼走 db.py 的 getpass，所以 docker exec 必須帶 -it（見 lib/compose.sh 的 db_cli_tty）。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

load_env
require_env COMPOSE_PROJECT_NAME

confirm "將建立一個擁有全部權限的超級管理者帳號，確定要繼續？"

db_cli_tty create-superuser
