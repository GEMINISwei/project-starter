#!/usr/bin/env bash
#
# 檢查與測試: make check [lint|contract|types|test|build|portable|integration] (不帶參數 = 前六項依序全跑)
#
#   make check               lint → contract → types → test → build → portable, 前後端都跑, 不需要 Docker (送出前跑這個)
#   make check lint          ruff + import-linter + eslint + dependency-cruiser + knip + shellcheck + compose 檔
#   make check contract      重產契約與前端型別到暫存目錄, 確認與 repo 裡的一致 (只讀, 不改檔)
#   make check types         mypy + tsc
#   make check test          pytest + vitest (帶覆蓋率), 沒有資料庫的 integration 測試會 skip
#   make check build         前端 production build
#   make check portable      把兩邊的 shared/ 單獨複製到空專案, 確認型別檢查與測試照樣通過
#   make check integration   起拋棄式 PostgreSQL 跑完整後端測試, 再確認 model 與 migration 一致
#
# 在主機上跑, 不是在容器裡 —— 那才是編輯器與 CI 看到的環境。首次執行前先跑 make init。
set -euo pipefail

# shellcheck source=scripts/lib/pg.sh
source "$(dirname "$0")/lib/pg.sh"
# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"
# shellcheck source=scripts/lib/contract.sh
source "$(dirname "$0")/lib/contract.sh"

# next.config.ts 在載入時會讀 UPLOAD_SIZE_LIMIT 之類的環境變數, build 前要先載入 .env。
load_env

step() { printf '\n── %s ──────────────────────────────────────────\n' "$1"; }

run_lint() {
    step "lint"
    (cd apps/api && uv run ruff check . && uv run lint-imports)
    (cd apps/web && npm run lint)
    lint_shell
    lint_compose
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
    shellcheck -x scripts/*.sh scripts/lib/*.sh .github/scripts/*.sh
}

# 用 .env.example 展開 dev 與 prod 兩組 compose: 抓 YAML 與錨點寫錯, 也抓「compose 用了
# `${X:?}` 但 .env.example 沒有 X」—— 後者否則要到有人照著範本開案才會炸。
# 必填項在範本裡是空的, 填個佔位值讓 `:?` 放行; `env -i` 隔開本機 .env 已經載入的變數,
# 不然本機有值就把範本的缺漏蓋過去了。
lint_compose() {
    command -v docker > /dev/null 2>&1 || { missing_tool docker; return; }
    local env_file mode
    env_file="$(mktemp)"
    sed 's/^\([A-Za-z_][A-Za-z0-9_]*\)=$/\1=placeholder/' .env.example > "${env_file}"
    for mode in dev prod; do
        # shellcheck disable=SC2016 # $1 要在子 shell 裡展開
        if ! env -i PATH="${PATH}" HOME="${HOME}" COMPOSE_ENV_FILE="${env_file}" \
            bash -c 'source scripts/lib/compose.sh && "$1_compose" config -q' _ "${mode}"; then
            rm -f "${env_file}"
            echo "${mode} 的 compose 設定展開失敗（見上方訊息）" >&2
            exit 1
        fi
    done
    rm -f "${env_file}"
}

run_types() {
    step "types"
    (cd apps/api && uv run mypy)
    (cd apps/web && npm run typecheck)
}

run_test() {
    step "test"
    # 後端輸出同時留一份下來數 skip。用 tee: 測試跑的時候要看得到進度。
    local log
    log="$(mktemp)"
    (cd apps/api && uv run pytest tests/ -q --cov) | tee "${log}"
    (cd apps/web && npm run test:coverage)

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
    (cd apps/web && npm run build)
}

# `shared/` 的承諾是「整包複製到別的專案就能用」。import 邊界由 lint 擋, 但漏掉的東西
# (放錯位置的測試、只定義在專案裡的設計變數、寫死的業務端點) 只有真的複製一次才看得到。
#
# 前端用「只有平台 schema」的契約編譯 (`apps/api/tests/shared/minimal_app.py` 產生):
# shared 引用了任何業務 entity 或端點, 這裡就是編譯錯誤。
run_portable() {
    step "portable：shared 單獨複製到空專案"
    local tmp
    tmp="$(mktemp -d)"
    trap 'rm -rf "'"${tmp}"'"' EXIT
    portable_api "${tmp}/api"
    portable_web "${tmp}/web" "${tmp}/api/openapi.json"
    echo "兩邊的 shared/ 都能單獨使用"
}

# 直接用專案的 venv, 不用 `uv run`: uv 會以專案目錄為準, 而這裡要的是「只看得到複製出去的
# 那一份 shared」。專案本身沒有安裝進 venv, 所以不會從 site-packages 混回原本的程式。
portable_api() {
    local dir="$1"
    local python="${REPO_ROOT}/apps/api/.venv/bin/python"
    mkdir -p "${dir}/tests"
    cp -R apps/api/shared "${dir}/"
    cp -R apps/api/tests/shared "${dir}/tests/"
    cp apps/api/tests/__init__.py apps/api/tests/conftest.py apps/api/tests/integration.py \
        "${dir}/tests/"
    cp apps/api/pyproject.toml "${dir}/"
    (
        cd "${dir}"
        "${python}" -m mypy shared tests
        "${python}" -m pytest -q -p no:cacheprovider tests
        "${python}" -c 'import json, sys
from tests.shared.minimal_app import CONTRACT_MODULE, create_minimal_app
json.dump(create_minimal_app(CONTRACT_MODULE).openapi(), sys.stdout)' > openapi.json
    )
}

portable_web() {
    local dir="$1" contract="$2"
    mkdir -p "${dir}/tests"
    cp -R apps/web/shared "${dir}/"
    cp -R apps/web/tests/shared apps/web/tests/stubs apps/web/tests/setup.ts "${dir}/tests/"
    # package.json 要一起帶: 少了它的 `"type": "module"`, vitest.config.ts 會被當成 CommonJS 載入。
    cp apps/web/package.json apps/web/tsconfig.json apps/web/vitest.config.ts "${dir}/"
    ln -s "${REPO_ROOT}/apps/web/node_modules" "${dir}/node_modules"
    # 原本的 next-env.d.ts 還引用 .next/ 底下產生的路由型別, 那屬於專案; 這裡只留框架型別。
    printf '/// <reference types="next" />\n' > "${dir}/next-env.d.ts"
    (
        cd "${dir}"
        npx openapi-typescript "${contract}" -o shared/api/generated/schema.d.ts > /dev/null
        npx tsc --noEmit -p .
        npx vitest run
    )
}

# 兩段都需要真的資料庫, 用拋棄式容器而不是 `make dev` 那個: 跑一次就會把開發資料洗掉。
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

# 排在 types 前面: 型別檔過期時 tsc 的錯誤看不出原因, 這裡先講清楚是契約沒更新。
run_contract() {
    step "contract"
    check_contract
    echo "契約與前端型別是最新的"
}

case "${1:-all}" in
    all)         run_lint; run_contract; run_types; run_test; run_build; run_portable ;;
    lint)        run_lint ;;
    types)       run_types ;;
    test)        run_test ;;
    build)       run_build ;;
    portable)    run_portable ;;
    integration) run_integration ;;
    contract)    run_contract ;;
    *)
        sed -n '/^#   make check/s/^#   //p' "$0" >&2
        exit 1
        ;;
esac
