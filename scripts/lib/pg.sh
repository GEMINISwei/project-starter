#!/usr/bin/env bash
#
# 起一個拋棄式的 PostgreSQL 容器, 給需要「真的資料庫」但不該碰開發資料的檢查用
# (`make check integration`、`make db migration`)。
#
# 為什麼不直接用 `make start` 起來的那個: 出廠的 compose 沒有把 PostgreSQL publish 到主機,
# 而且那份資料是開發用的 —— 跑一次 integration 測試就把它洗掉。
#
# 這支是被 source 的, 所以刻意**不**寫 `set -euo pipefail` (同 common.sh)。

[ -n "${PG_SH_LOADED:-}" ] && return 0
PG_SH_LOADED=1

# shellcheck source=scripts/lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

readonly THROWAWAY_PG_USER=test
readonly THROWAWAY_PG_DB=test

require_docker() {
    if ! command -v docker > /dev/null 2>&1 || ! docker info > /dev/null 2>&1; then
        echo "需要可用的 docker（這支要起一個拋棄式的 PostgreSQL 容器）。" >&2
        return 1
    fi
}

# 用法: start_throwaway_postgres <容器名稱>
#
# 成功後設定 THROWAWAY_PG_URL (主機端連線字串)。
#
# 主機 port 交給 docker 挑、只綁 127.0.0.1: 固定 port 會撞到主機上的 PostgreSQL,
# `make check integration` 與 `make db migration` 也不能同時跑; 綁 0.0.0.0 則是把一個
# 密碼為 test 的資料庫開給整個區網。
# 呼叫端負責 `trap` 清理 —— 這裡不代設, 因為 trap 是整支腳本共用的資源,
# 由被 source 的檔案偷偷設掉會蓋掉呼叫端自己的。
start_throwaway_postgres() {
    local container="$1"
    local compose="infra/docker/docker-compose.yml"

    # image 從 compose 讀出來, 不在這裡寫第二份 —— 升 postgres 版本時只改 compose。
    local image
    image="$(grep -oE 'postgres:[0-9]+\.[0-9]+-alpine' "${compose}" | head -1)"
    if [ -z "${image}" ]; then
        # 訊息要帶上路徑: 「找不到 image」與「檔案根本不在這裡」是兩回事。
        echo "在 ${compose} 找不到 postgres image" >&2
        return 1
    fi

    # 上一次被 Ctrl-C 中斷時可能留下同名容器; 先清掉, 不然 docker run 會說名稱已被使用。
    docker rm -f "${container}" > /dev/null 2>&1 || true

    echo "啟動拋棄式 PostgreSQL（${image}）…"
    if ! docker run -d --name "${container}" -p "127.0.0.1::5432" \
        -e "POSTGRES_USER=${THROWAWAY_PG_USER}" \
        -e "POSTGRES_PASSWORD=${THROWAWAY_PG_USER}" \
        -e "POSTGRES_DB=${THROWAWAY_PG_DB}" \
        "${image}" > /dev/null; then
        return 1
    fi

    # `-h 127.0.0.1` 是必要的 (同 CI 與 compose 的 healthcheck): 不帶主機時 pg_isready 走
    # unix socket, 而那個 socket 在 initdb 期間就已經在了, 檢查會提早轉綠。
    for _ in $(seq 1 30); do
        if docker exec "${container}" pg_isready -h 127.0.0.1 \
            -U "${THROWAWAY_PG_USER}" -d "${THROWAWAY_PG_DB}" > /dev/null 2>&1; then
            local port
            port="$(docker port "${container}" 5432/tcp | head -1)"
            port="${port##*:}"
            THROWAWAY_PG_URL="postgresql+asyncpg://${THROWAWAY_PG_USER}:${THROWAWAY_PG_USER}@127.0.0.1:${port}/${THROWAWAY_PG_DB}"
            export THROWAWAY_PG_URL
            return 0
        fi
        sleep 1
    done

    echo "PostgreSQL 未能在時限內接受連線。容器日誌：" >&2
    docker logs "${container}" >&2 || true
    return 1
}
