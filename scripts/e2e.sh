#!/usr/bin/env bash
#
# 開發中反覆跑 E2E: make e2e <子指令> (development only)
#
#   make e2e up              起一套這個 checkout 專用的 E2E 環境 (dev mode, 改了原始碼不必重建); 已經起著就沿用
#   make e2e test <檔案...>   重設資料、重啟 api, 再只跑那幾個 spec
#   make e2e grep "名稱"      同上, 只跑名稱符合的測試
#   make e2e down            拆掉這套環境, 連資料一起刪
#
# 跟 `make check e2e` 分工: 那邊每次用正式環境的 image 起一套新的、跑整套, 是 CI 的必要檢查;
# 這邊常駐、用 dev mode, 給「改一點、跑相關的那幾個」的迴圈用 (理由見 docs/decisions/0009)。
#
# 每個 checkout 一套: compose 專案名稱取自 checkout 的路徑, port 與帳密記在 git 目錄裡
# (不會被 commit; worktree 各有自己的 git 目錄, 所以各有一套)。原始碼是 bind mount 的,
# 一個 checkout 同時只有一份原始碼, 依分支分反而會讓切換分支後的舊環境掛著別的程式碼。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

usage() {
    sed -n '/^#   make e2e/s/^#   //p' "$0" >&2
    exit 1
}

load_env
deny_on_production "make e2e"
require_env COMPOSE_PROJECT_NAME

STATE="$(git -C "${REPO_ROOT}" rev-parse --absolute-git-dir)/e2e-stack.env"
readonly STATE

# `make check e2e` 預設用 3900, 從下一個開始找沒人在聽的。
free_port() {
    local port
    for port in $(seq 3901 3999); do
        if ! (exec 3<> "/dev/tcp/127.0.0.1/${port}") 2> /dev/null; then
            echo "${port}"
            return
        fi
    done
    echo "3901 到 3999 都有人在用，找不到空的 port" >&2
    exit 1
}

# 密碼與金鑰每套隨機產生, 只存在這份檔案 (權限只給自己)。它同時是 compose 的 env file:
# 值都是英數與 base64, 不需要引號, 兩邊讀起來一樣。
new_stack() {
    local name
    name="${COMPOSE_PROJECT_NAME}-e2e-$(printf '%s' "${REPO_ROOT}" | cksum | awk '{ print $1 }')"
    (
        umask 077
        {
            echo "MODE=development"
            echo "COMPOSE_PROJECT_NAME=${name}"
            echo "SYSTEM_NAME=E2E"
            echo "SYSTEM_PORT=$(free_port)"
            echo "EXPIRE_HOURS=1"
            echo "POSTGRES_PASSWORD=$(openssl rand -hex 32)"
            echo "JWT_SECRET_KEY=$(openssl rand -hex 32)"
            echo "NEXT_SERVER_ACTIONS_ENCRYPTION_KEY=$(openssl rand -base64 32)"
            echo "E2E_ADMIN_USERNAME=e2e-admin"
            echo "E2E_ADMIN_PASSWORD=$(openssl rand -hex 16)"
        } > "${STATE}"
    )
}

# shell 的環境變數優先於 --env-file, 所以兩邊給同一組值: 開發機的 .env 已經載入了自己的專案名稱與 port。
load_state() {
    set -a
    # shellcheck source=/dev/null
    source "${STATE}"
    set +a
    export COMPOSE_ENV_FILE="${STATE}"
    # 用 localhost 不用 127.0.0.1: next dev 只對 localhost 開放 /_next 的開發資源, 其他來源會被擋,
    # 頁面不會 hydrate, 按鈕按了沒反應 (實測; 錯誤只出現在 web 容器的 log)。
    BASE_URL="http://localhost:${SYSTEM_PORT}"
}

require_stack() {
    if [ ! -f "${STATE}" ]; then
        echo "這個 checkout 還沒有 E2E 環境，請先 make e2e up" >&2
        exit 1
    fi
    load_state
    if ! container_running "${COMPOSE_PROJECT_NAME}-api"; then
        echo "E2E 環境（${COMPOSE_PROJECT_NAME}）沒有在執行，請先 make e2e up" >&2
        exit 1
    fi
}

cmd_up() {
    [ -f "${STATE}" ] || new_stack
    load_state
    app_compose run --rm -T migrate
    app_compose up -d --wait --remove-orphans
    # next dev 第一次打開頁面時才編譯, 先打一次, 第一個測試才不會被編譯時間拖到逾時。
    curl -fsS -o /dev/null --max-time 180 "${BASE_URL}/login" \
        || echo "預先載入 ${BASE_URL}/login 失敗，第一個測試可能會比較慢" >&2
    echo "E2E 環境：${BASE_URL}（${COMPOSE_PROJECT_NAME}）"
    echo "  make e2e test [檔案...]／make e2e grep \"名稱\" 跑測試，make e2e down 拆掉"
}

# 每次從同一個起點開始: 清空資料重建、超管重建, 再重啟 api —— 登入限流的計數放在行程記憶體
# (docs/decisions/0004), 不重啟的話, 連跑幾次就會撞到同一個 IP 的上限。
# 用 && 串起來: 呼叫端在 `if ! output="$(…)"` 裡, 那裡的 set -e 不生效, 中途失敗不會停下。
reset_stack() {
    db_cli reset \
        && db_cli migrate \
        && printf '%s\n' "E2E 超管" "${E2E_ADMIN_USERNAME}" "${E2E_ADMIN_PASSWORD}" \
            "${E2E_ADMIN_PASSWORD}" | db_cli_stdin create-superuser \
        && app_compose restart api \
        && app_compose up -d --wait
}

# 呼叫端先 require_stack: test 要先確認環境在, 才輪到檢查有沒有給檔案。
cmd_test() {
    [ -d e2e/node_modules ] || { echo "缺少 e2e 的套件：cd e2e && npm ci" >&2; exit 1; }
    (cd e2e && npm run --silent typecheck)
    # 這幾步成功時的輸出 (compose 的進度、建立超管的提示) 每次十幾行, 只在失敗時整段印出來。
    local output
    if ! output="$(reset_stack 2>&1)"; then
        echo "${output}" >&2
        echo "重設 E2E 環境失敗（見上方訊息）" >&2
        exit 1
    fi
    (
        cd e2e
        npx playwright install chromium > /dev/null
        E2E_BASE_URL="${BASE_URL}" npx playwright test "$@"
    )
}

cmd_down() {
    if [ ! -f "${STATE}" ]; then
        echo "這個 checkout 沒有 E2E 環境"
        return
    fi
    load_state
    app_compose down -v --remove-orphans
    # image 名稱帶著這套的專案名稱, 不清的話每個 checkout 各留一份標籤; 層與開發中那套共用, 只拿掉標籤。
    docker image rm "${COMPOSE_PROJECT_NAME}-api:latest" "${COMPOSE_PROJECT_NAME}-web:latest" \
        > /dev/null 2>&1 || true
    rm -f "${STATE}"
}

cd "${REPO_ROOT}"
case "${1:-}" in
    up)   [ "$#" -eq 1 ] || usage; cmd_up ;;
    test)
        shift
        require_stack
        # 漏帶檔案就默默跑完全部, 一輪從十幾秒變成好幾分鐘。整套交給正式環境的版本 (與 CI 相同);
        # 真的要在 dev 環境跑全部 (量這套環境本身時), 給 `spec` 這個符合所有檔名的篩選。
        if [ "$#" -eq 0 ]; then
            echo "make e2e test 要指定 spec 檔案；要跑整套請用 make check e2e" >&2
            exit 1
        fi
        cmd_test "$@"
        ;;
    grep)
        if [ "$#" -ne 2 ] || [ -z "$2" ]; then usage; fi
        require_stack
        cmd_test --grep "$2"
        ;;
    down) [ "$#" -eq 1 ] || usage; cmd_down ;;
    *)    usage ;;
esac
