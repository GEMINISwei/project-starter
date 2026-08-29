#!/usr/bin/env bash
#
# 跑跨層 e2e：起一套用完就丟的 dev stack、跑 playwright、收掉。
#
# **e2e 只測跨層接縫**（見 docs/development.md 的「e2e 的範圍」）。單層測得到的東西一律不進
# e2e/ —— 不設這條的話它三個月後會長成第二套測試套件，然後因為慢又不穩而沒有人看。
#
# **它是 dev，只是不是「你的」那套 dev。** 跑的就是 MODE=development，但用另一個 project name
# 拿到自己的 volume：第一條接縫測的是「還沒有超級管理者的系統」，而你的開發環境早就 bootstrap
# 過了。那套 stack 平常不存在，這支建起來、跑完收掉。
#
# ── 為什麼 playwright 不做成 compose 裡的一個服務 ─────────────────────────────
#
# 那是下一個人會想試的做法（「compose 裡再加一個服務就好」），實際評估過，不划算：
#
#   - 官方 image 約 2GB（含三種瀏覽器）。開發機是一次性的，但 **CI runner 每次都是乾淨的**
#     —— 等於每個 PR 多拉 2GB，換掉的只是 host 上 18MB 的 node_modules。
#   - image 裡沒有 tsc 也沒有 @types/node，型別檢查那步要另外用 npx 拉、還要自己掛快取。
#   - config 頂端的 `import ... from "@playwright/test"` 得靠 NODE_PATH 解到全域安裝的
#     那一份，而 NODE_PATH 只對 CommonJS 生效 —— 哪天有人把 e2e 標成 ESM 就會壞，
#     錯誤訊息是「Cannot find module」，看起來像沒安裝。
#   - 容器裡沒有 headed 模式與 `--ui` —— 而那正是 E2E_HEADED 與參數轉發買到的東西
#     （見檔尾），搬進容器就全部拿不到，寫測試時只能看 trace。
#
# 唯一真正的好處是「不必 publish host port」，但**多專案搶 port 那件事由底下的
# SYSTEM_PORT=0 就解決了**，跟 playwright 跑在哪裡無關。兩件事不要綁在一起。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

load_env
require_env COMPOSE_PROJECT_NAME REGISTER_KEY

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME}-e2e"
# nginx 那邊寫的是 `ports: ${SYSTEM_PORT:?}:80`，沒辦法不 publish。給 0 讓作業系統配一個沒人用
# 的臨時 port，所以同時開好幾個專案跑 e2e 也不會撞。實際配到哪個由底下的 resolve_port 問出來。
#
# 這兩行蓋得過 `.env` 是因為 **shell 的環境變數優先於 `--env-file`** ——
# 那是 compose 的既有行為，不是這裡做了什麼特別的事。
export SYSTEM_PORT=0

readonly E2E_DIR="$REPO_ROOT/e2e"

if [ ! -f "$E2E_DIR/package-lock.json" ]; then
    echo "找不到 e2e/package-lock.json。先跑一次 (cd e2e && npm install) 並把 lock 檔進版控 ——" >&2
    echo "  這個 repo 的相依一律釘死，e2e 不例外（見 docs/development.md 的相依升級紀律）。" >&2
    exit 1
fi

teardown() {
    # **第一行就要取 $?**，後面任何一個指令都會蓋掉它。
    local status=$?

    # 失敗時先把容器 log 倒出來，**一定要在 down 之前** —— 收掉之後就沒得問了。
    #
    # 這一段守的是最難查的那種失敗：stack 根本沒起來。那時 playwright 一步都沒跑，
    # html 報告與 trace 都是空的，CI 上看到的只有一個紅燈和「暖機超時」。
    # 真正的原因（migrate 失敗、web 編譯失敗、環境變數少一個）只在 log 裡。
    if [ "$status" -ne 0 ]; then
        mkdir -p "$E2E_DIR/test-results"
        {
            # `ps -a` 先來：它分得出「健康檢查沒過」與「容器直接退出」——
            # 兩者在 compose 的錯誤訊息裡都叫 unhealthy，但要查的方向完全不同。
            # 退出碼與 Status 欄只有這裡看得到。
            echo "===== compose ps -a ====="
            dev_compose ps -a
            echo
            echo "===== logs ====="
            dev_compose logs --no-color --tail 200
        } > "$E2E_DIR/test-results/docker-logs.txt" 2>&1 || true
        echo "容器狀態與 log 已存到 e2e/test-results/docker-logs.txt" >&2
    fi

    if [ -n "${E2E_KEEP:-}" ]; then
        echo
        echo "E2E_KEEP 有設，保留環境：${COMPOSE_PROJECT_NAME}（${base_url:-尚未取得位址}）"
        echo "  收掉：docker compose -p ${COMPOSE_PROJECT_NAME} down -v"
        return
    fi
    dev_compose down -v --remove-orphans > /dev/null 2>&1 || true
}
base_url=""
trap teardown EXIT

echo "起 e2e 環境：${COMPOSE_PROJECT_NAME}"
dev_compose down -v --remove-orphans > /dev/null 2>&1 || true
# --wait：等到有 healthcheck 的服務（postgres、api、web）都健康才往下，
# 不然第一個 page.goto 會撞在還沒起來的 nginx 上，而症狀是超時、不是「服務沒起來」。
dev_compose up -d --wait

# `compose port` 回的是 `0.0.0.0:54321`（IPv6 時是 `[::]:54321`），取最後一個冒號之後。
resolve_port() {
    local mapping
    mapping="$(dev_compose port nginx 80)"
    [ -n "$mapping" ] || { echo "問不到 nginx 的對外 port" >&2; return 1; }
    printf '%s' "${mapping##*:}"
}
base_url="http://localhost:$(resolve_port)"
echo "對外位址：${base_url}"

# ── 暖機。**不要拿掉這一段** ──────────────────────────────────────────────────
#
# web 的 healthcheck 探的是 `/healthz`（見 docker-compose.yml 的註解），那條路由編譯很快，
# 所以 `--wait` 通過**不代表首頁可以用**：dev 模式下 `next dev` 是在第一次請求某條路由時
# 才編譯它，首頁那一棵要數十秒。
#
# 少了這段的症狀是「第一支測試 timeout，重跑一次就過了」—— 看起來像 e2e 不穩定，實際上是在量
# 編譯時間。而 playwright 刻意設了 retries: 0，所以那會直接是紅燈。
warmup() {
    local deadline=$(($(date +%s) + 180))

    printf '暖機（等 next dev 編譯首頁）'
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if curl -fsS -L -o /dev/null --max-time 60 "${base_url}/"; then
            echo " 好了"
            return 0
        fi
        printf '.'
        sleep 3
    done

    echo >&2
    echo "首頁在 180 秒內沒有回應（${base_url}）。用 E2E_KEEP=1 重跑一次再看 make logs。" >&2
    return 1
}
warmup

cd "$E2E_DIR"
npm ci

# CI 的 runner 是乾淨的 ubuntu，瀏覽器的系統相依要一起裝；本機通常已經有了，
# 而 --with-deps 在 macOS 上會要求提權，所以只在 CI 帶。
# 瀏覽器的版本兩邊一致：它由 @playwright/test 的版本釘死，而那由 package-lock.json 保證。
if [ -n "${CI:-}" ]; then
    npx playwright install --with-deps chromium
else
    npx playwright install chromium
fi

# 型別檢查刻意放在這裡，不在 `make typecheck` —— 那支要能離線快跑，而這裡本來就已經
# `npm ci` 過了。**代價要知道：e2e 的型別錯誤要到 `make e2e` 才浮出來。**
npx tsc --noEmit

# ── 參數轉給 playwright ─────────────────────────────────────────────────────
#
# `npm test` 後面的 `--` 不能省：npm 會把 `--` 之前的旗標當成**自己的**設定吃掉，
# `npm test --headed` 的結果是 playwright 一個參數都沒收到，而且不會有錯誤訊息。
# 沒帶參數時 `npm test --` 與 `npm test` 完全相同，不必另外分支。
#
# `"$@"` 在零參數下是安全的：`set -u` 的 unbound 陷阱只發生在**具名陣列**
#（`"${arr[@]}"` 在 macOS 的 bash 3.2 會當場報錯），`$@` 是特例。
#
# `--headed` 另外翻成環境變數：playwright 的 worker 是另一個行程、會再載一次 config，
# 那裡的 process.argv 沒有這個旗標 —— 靠 argv 判斷會讓主行程與 worker 拿到不同的
# slowMo 與 timeout，而且完全沒有訊息。config 只讀環境變數就沒有這個問題。
case " $* " in *" --headed "*) export E2E_HEADED=1 ;; esac

E2E_BASE_URL="$base_url" REGISTER_KEY="$REGISTER_KEY" npm test -- "$@"
