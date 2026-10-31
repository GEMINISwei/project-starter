#!/usr/bin/env bash
#
# 檢查與測試: make check [lint|contract|migrate|types|test|build|integration|e2e] (不帶參數 = 前六項依序全跑)
#
#   make check               lint → contract → migrate → types → test → build, 前後端都跑, 不需要 Docker (送出前跑這個)
#   make check lint          ruff + import-linter + eslint + dependency-cruiser + knip + shellcheck + compose 檔
#   make check contract      重產契約與前端型別到暫存目錄, 確認與 repo 裡的一致 (只讀, 不改檔)
#   make check migrate       已發版的 migration 沒有被修改或刪除 (和最近的 release tag 比對)
#   make check types         mypy + tsc
#   make check test          pytest + vitest (帶覆蓋率), 沒有資料庫的 integration 測試會 skip
#   make check build         前端 production build, 並確認 Next 有認到 proxy.ts
#   make check integration   起拋棄式 PostgreSQL 跑完整後端測試, 再確認 model 與 migration 一致
#   make check e2e           起一套拋棄式的正式環境, 用 Playwright 從瀏覽器跑過整條路 (e2e/)
#
# 在主機上跑, 不是在容器裡 —— 那才是編輯器與 CI 看到的環境。首次執行前先跑 make init dev。
set -euo pipefail

# shellcheck source=scripts/lib/pg.sh
source "$(dirname "$0")/lib/pg.sh"
# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"
# shellcheck source=scripts/lib/contract.sh
source "$(dirname "$0")/lib/contract.sh"
# shellcheck source=scripts/lib/migrations.sh
source "$(dirname "$0")/lib/migrations.sh"

# deny_on_production 看的是 .env 的 MODE, 要先載入。
load_env
deny_on_production "make check"

step() { printf '\n── %s ──────────────────────────────────────────\n' "$1"; }

# npm 一律 `--silent`: 不回顯 `> web@0.0.1 lint` 這類指令列 (巢狀的 npm run 也跟著安靜)。
# 通過時的輸出越短越好, AI agent 一次任務會跑好幾次, 每次都要整段讀進上下文; 錯誤訊息不受影響。

run_lint() {
    step "lint"
    # .agents/hooks/ 的 hook 腳本不在 api 的 import root 裡, 但同樣是 Python, 套用 api 的 ruff 設定。
    (cd apps/api && uv run ruff check . ../../.agents/hooks && uv run lint-imports)
    (cd apps/web && npm run --silent lint)
    lint_shell
    lint_compose
    warn_git_hooks
}

# .githooks/ 要 core.hooksPath 指過去才會生效, 沒設時 commit 照樣成功、不會有任何提示。
# 只提醒不擋: 這是本機設定, CI 上本來就沒有。
warn_git_hooks() {
    [ -n "${CI:-}" ] && return
    [ "$(git config --get core.hooksPath || true)" = ".githooks" ] && return
    echo "⚠️  git hook 沒有啟用（.githooks/ 的 commit-msg 不會檢查）：重跑 make init dev，"
    echo "   或 git config core.hooksPath .githooks。"
}

# 本機沒裝工具時只提醒、不擋 (`make check` 的承諾是不需要額外安裝); CI 上 (GitHub 會設
# CI=true) 一律當成失敗, 否則整項檢查會在沒人發現的情況下消失。
missing_tool() {
    if [ -n "${CI:-}" ]; then
        echo "CI 上缺少 $1" >&2
        exit 1
    fi
    echo "⚠️  沒有安裝 $1，略過這一項（CI 會跑）。"
}

lint_shell() {
    command -v shellcheck > /dev/null 2>&1 || { missing_tool shellcheck; return; }
    # -x: 跟著 `source` 進 lib/, 被引用的函式與變數才不會被當成未定義。
    shellcheck -x scripts/*.sh scripts/lib/*.sh .github/scripts/*.sh .agents/skills/*/scripts/*.sh \
        .githooks/*
}

# 用 .env.example 展開兩種 MODE 的 compose: 抓 YAML 與錨點寫錯, 也抓「compose 用了
# `${X:?}` 但 .env.example 沒有 X」—— 後者否則要到有人照著範本開案才會炸。
# 必填項在範本裡是空的, 填個佔位值讓 `:?` 放行; `env -i` 隔開本機 .env 已經載入的變數,
# 不然本機有值就把範本的缺漏蓋過去了。
lint_compose() {
    command -v docker > /dev/null 2>&1 || { missing_tool docker; return; }
    local env_file mode
    env_file="$(mktemp)"
    sed 's/^\([A-Za-z_][A-Za-z0-9_]*\)=$/\1=placeholder/' .env.example > "${env_file}"
    for mode in development production; do
        if ! env -i PATH="${PATH}" HOME="${HOME}" COMPOSE_ENV_FILE="${env_file}" MODE="${mode}" \
            bash -c 'source scripts/lib/compose.sh && app_compose config -q'; then
            rm -f "${env_file}"
            echo "${mode} 的 compose 設定展開失敗（見上方訊息）" >&2
            exit 1
        fi
    done
    rm -f "${env_file}"
}

# 部署判斷資料庫「一致」靠的是 revision id: 已發版的 migration 被改了內容而 id 不變的話,
# 那道檢查會誤判成一致, 改過的結構也永遠不會套用到已經跑過它的資料庫上。
run_migrate() {
    step "migrate"
    check_released_migrations apps/api/migrations/versions
}

run_types() {
    step "types"
    (cd apps/api && uv run mypy)
    (cd apps/web && npm run --silent typecheck)
}

run_test() {
    step "test"
    # 後端輸出同時留一份下來數 skip。用 tee: 測試跑的時候要看得到進度。
    local log
    log="$(mktemp)"
    (cd apps/api && uv run pytest tests/ -q --cov) | tee "${log}"
    (cd apps/web && npm run --silent test:coverage)

    # skip 的 exit code 是 0, 不講的話「資料庫沒起來」跟「全部通過」看起來一樣。
    local skipped
    skipped="$(sed -n 's/.*[^0-9]\([0-9][0-9]*\) skipped.*/\1/p' "${log}" | tail -1)"
    rm -f "${log}"
    if [ -n "${skipped}" ] && [ "${skipped}" -gt 0 ]; then
        echo
        echo "⚠️  後端有 ${skipped} 個 integration 測試被 skip（本機沒有資料庫）。"
        echo "   動到資料庫相關的程式時，跑 make check integration。"
    fi
}

run_build() {
    step "build"
    local log
    log="$(mktemp)"
    (cd apps/web && npm run --silent build) | tee "${log}"
    # proxy.ts 放錯位置或匯出名稱不對時, Next 照樣 build 成功, 只是路由保護整層消失。
    if ! grep -q 'Proxy (Middleware)' "${log}"; then
        rm -f "${log}"
        echo "build 輸出沒有 Proxy (Middleware)：Next 沒認到 apps/web/proxy.ts，路由保護不會生效" >&2
        exit 1
    fi
    rm -f "${log}"
}

# 兩段都需要真的資料庫, 用拋棄式容器而不是 `make start` 那個: 跑一次就會把開發資料洗掉。
#
# 1. `REQUIRE_INTEGRATION=1` 把「連不上就 skip」變成「連不上就 fail」。
# 2. `alembic check` 擋「改了 model 卻沒寫 migration」—— 測試資料庫是從 model 現建的,
#    那種錯測試永遠抓不到, 只有部署之後第一次讀寫那個欄位才炸。
# CI 的 integration job 跑的就是這一段 (見 .github/workflows/ci.yml)。
run_integration() {
    require_env COMPOSE_PROJECT_NAME
    local container="${COMPOSE_PROJECT_NAME}-test-postgres"
    require_docker
    start_throwaway_postgres "${container}"
    trap 'docker rm -f "'"${container}"'" > /dev/null 2>&1 || true' EXIT

    export PROJECT_NAME=test MODE=development POSTGRES_URL="${THROWAWAY_PG_URL}"
    export JWT_SECRET_KEY=test_secret_key_that_is_at_least_32_characters

    step "integration：完整後端測試"
    (cd apps/api && REQUIRE_INTEGRATION=1 uv run pytest tests/ -q --cov)

    step "integration：model 與 migration 一致（alembic check）"
    # 先清掉測試留下的表, 讓結構完全由 migration 建出來。
    docker exec "${container}" psql -q -U "${THROWAWAY_PG_USER}" -d "${THROWAWAY_PG_DB}" \
        -c 'DROP SCHEMA public CASCADE' -c 'CREATE SCHEMA public'
    (cd apps/api && uv run alembic upgrade head)
    if ! (cd apps/api && uv run alembic check); then
        echo >&2
        echo "model 與 migration 對不上：上面列出的變更沒有對應的 migration。" >&2
        echo "  產生一支：make db migration \"說明\"，產生完**要自己讀一遍**。" >&2
        exit 1
    fi
    echo "model 與 migration 一致"
}

# 瀏覽器 → nginx → web → api → PostgreSQL 整條路的測試 (e2e/)。跟 integration 一樣用拋棄式的
# 環境: 另起一套 compose 專案 (`<專案>-e2e`, 自己的 port 與 volume), 跑完整套連 volume 刪掉,
# 開發中的那套不受影響。用 production 的 image 與 nginx 模板, 測的才是要上線的那份。
#
# 不經過 `make start`: 那條路要求停在發版的 tag 上。啟動順序照抄它 (先單獨跑 migrate 再 up)。
# 全部在子 shell 裡跑: 這裡 export 的 MODE 與專案名稱不能漏到呼叫端。
run_e2e() (
    require_env COMPOSE_PROJECT_NAME
    require_docker
    [ -d e2e/node_modules ] || { echo "缺少 e2e 的套件：cd e2e && npm ci" >&2; exit 1; }

    step "e2e：型別檢查"
    (cd e2e && npm run typecheck)

    # shell 的環境變數優先於 --env-file, 所以兩邊給同一組值: 開發機已經載入 .env 的
    # MODE=development 會蓋過檔案裡的值。檔案本身也要有, compose 少了它會直接失敗。
    export MODE=production
    export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME}-e2e"
    export SYSTEM_NAME=E2E
    export SYSTEM_PORT="${E2E_PORT:-3900}"
    export EXPIRE_HOURS=1
    POSTGRES_PASSWORD="$(openssl rand -hex 32)"
    JWT_SECRET_KEY="$(openssl rand -hex 32)"
    NEXT_SERVER_ACTIONS_ENCRYPTION_KEY="$(openssl rand -base64 32)"
    export POSTGRES_PASSWORD JWT_SECRET_KEY NEXT_SERVER_ACTIONS_ENCRYPTION_KEY
    COMPOSE_ENV_FILE="$(mktemp)"
    export COMPOSE_ENV_FILE
    local name
    for name in MODE COMPOSE_PROJECT_NAME SYSTEM_NAME SYSTEM_PORT EXPIRE_HOURS \
        POSTGRES_PASSWORD JWT_SECRET_KEY NEXT_SERVER_ACTIONS_ENCRYPTION_KEY; do
        printf '%s=%s\n' "${name}" "${!name}" >> "${COMPOSE_ENV_FILE}"
    done
    trap 'app_compose down -v --remove-orphans > /dev/null 2>&1 || true; rm -f "${COMPOSE_ENV_FILE}"' EXIT

    step "e2e：建置並啟動拋棄式的正式環境（${COMPOSE_PROJECT_NAME}）"
    app_compose build
    app_compose run --rm -T migrate
    app_compose up -d --remove-orphans
    # up 會等 api 與 web 的 healthcheck 才啟動 nginx, 但 nginx 自己沒有 healthcheck。
    local base_url="http://127.0.0.1:${SYSTEM_PORT}" attempt
    for attempt in $(seq 30); do
        curl -fsS -o /dev/null "${base_url}/healthz" && break
        [ "${attempt}" = 30 ] && { echo "nginx 沒有在時限內回應：${base_url}" >&2; exit 1; }
        sleep 1
    done

    # 超管只能從 CLI 建立 (網頁上沒有入口)。帳密每次隨機, 只存在這次執行的環境變數裡。
    export E2E_BASE_URL="${base_url}"
    export E2E_ADMIN_USERNAME=e2e-admin
    E2E_ADMIN_PASSWORD="$(openssl rand -hex 16)"
    export E2E_ADMIN_PASSWORD
    printf '%s\n' "E2E 超管" "${E2E_ADMIN_USERNAME}" "${E2E_ADMIN_PASSWORD}" "${E2E_ADMIN_PASSWORD}" \
        | db_cli_stdin create-superuser > /dev/null

    step "e2e：Playwright"
    # 已經下載過時不會重抓。CI 另外用 --with-deps 裝系統套件 (見 .github/workflows/ci.yml)。
    (cd e2e && npx playwright install chromium && npm test)
)

# 排在 types 前面: 型別檔過期時 tsc 的錯誤看不出原因, 這裡先講清楚是契約沒更新。
run_contract() {
    step "contract"
    check_contract
    echo "契約與前端型別是最新的"
}

case "${1:-all}" in
    all)         run_lint; run_contract; run_migrate; run_types; run_test; run_build ;;
    lint)        run_lint ;;
    types)       run_types ;;
    test)        run_test ;;
    build)       run_build ;;
    integration) run_integration ;;
    e2e)         run_e2e ;;
    contract)    run_contract ;;
    migrate)     run_migrate ;;
    *)
        sed -n '/^#   make check/s/^#   //p' "$0" >&2
        exit 1
        ;;
esac
