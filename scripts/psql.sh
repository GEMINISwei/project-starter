#!/usr/bin/env bash
#
# 進入 PostgreSQL 的 psql shell。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

load_env
require_env COMPOSE_PROJECT_NAME POSTGRES_USER POSTGRES_DB

# 密碼走容器內的 PGPASSWORD 而不是連線字串：連線字串會出現在容器的 `ps` 輸出裡。
docker exec -it -e PGPASSWORD="$POSTGRES_PASSWORD" "${COMPOSE_PROJECT_NAME}-postgres" \
    psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"
