#!/usr/bin/env bash
#
# 啟動服務: make start (依 .env 的 MODE)
#
#   make start   啟動 postgres → migrate → api → web → nginx (會自動跑 migration); production 會重新建置或拉 image
#   make start lan   (僅 development) 同上, 但對區網開放, 讓手機連進來測試; 下次一般的 make start 就關回去
#
# development 用 bind mount 的原始碼, 改了直接生效, 不必建置。
#
# `lan` 不寫進 .env 而是每次啟動時給: 常駐的話帶著筆電到外面的 Wi-Fi 也照樣開著。
# 沒給時明確設回 loopback, 不沿用 shell 裡留下的 DEV_BIND_ADDRESS。
#
# production 預設 `--build`: 要確定跑的是目前這份原始碼建出來的 image。shell 有匯出 API_IMAGE 與
# WEB_IMAGE 時改成從 registry 拉 (deploy workflow 走這條, 見 docs/operations.md〈自動部署〉), 而且
# **不能帶 `--build`**: 實測 `--build` 會蓋過 `pull_policy: always`, 照樣在主機上建置, 還把建出來的
# 東西標成 registry 的 image 名稱。兩個要一起給 —— 只給一個的話, 另一個會去 Docker Hub 拉
# `<專案>-web:latest` 之類不存在的 image。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

usage() {
    sed -n '/^#   make start/s/^#   //p' "$0" >&2
    exit 1
}

# 正式環境只從發版的 tag 啟動: 主機上 `git pull` 了 main 再啟動, 等於上線一份沒發版、沒經過 CI
# 的程式碼。比對 tag 指到的 commit 而不是 `git describe`: 同一個 commit 可能有好幾個 tag。
require_release_checkout() {
    local version tagged head
    version="$(app_version)"
    tagged="$(git rev-parse --quiet --verify "refs/tags/v${version}^{commit}" 2> /dev/null || true)"
    head="$(git rev-parse --quiet --verify HEAD 2> /dev/null || true)"
    if [ -z "${tagged}" ] || [ "${tagged}" != "${head}" ]; then
        echo "正式環境只能從發版的 tag 啟動：HEAD 要停在 v${version}" >&2
        echo "  git fetch --tags && git checkout v${version}" >&2
        exit 1
    fi
}

# 印給手機輸入的網址。取不到 IP (沒連網路、介面名稱不同) 時只提示, 不讓啟動失敗。
print_lan_urls() {
    local address="" host interface
    for interface in en0 en1; do
        address="$(ipconfig getifaddr "${interface}" 2> /dev/null || true)"
        [ -n "${address}" ] && break
    done
    if [ -z "${address}" ]; then
        address="$(hostname -I 2> /dev/null | awk '{ print $1 }' || true)"
    fi
    host="$(scutil --get LocalHostName 2> /dev/null || true)"
    if [ -n "${address}" ]; then
        echo "區網：http://${address}:${SYSTEM_PORT}"
    fi
    if [ -n "${host}" ]; then
        echo "區網：http://${host}.local:${SYSTEM_PORT}（換 Wi-Fi 也不變）"
    fi
    if [ -z "${address}${host}" ]; then
        echo "區網：找不到這台電腦的區網 IP，請自行查詢後用 http://<IP>:${SYSTEM_PORT} 連線"
    fi
    echo "同一個網路上的人都連得到，用完跑一次 make start 關回只限本機"
}

# 模板寫錯的話, 重建後的 nginx 起不來, 整個站就停了。先用一次性的容器 (同樣的 image、mount 與
# 環境變數, 官方 entrypoint 會照常展開模板) 跑 `nginx -t`, 不過就在 up 之前停下, 線上的 nginx
# 原樣不動。不帶 --service-ports, 不會跟跑著的 nginx 搶 port。
check_nginx_config() {
    local output
    if ! output="$(app_compose run --rm --no-deps -T nginx nginx -t 2>&1)"; then
        echo "${output}" >&2
        echo "nginx 設定檢查失敗（見上方訊息），沒有啟動；線上的 nginx 維持原樣" >&2
        exit 1
    fi
}

lan=false
case "$#:${1:-}" in
    0:) ;;
    1:lan) lan=true ;;
    *) usage ;;
esac
load_env
require_env COMPOSE_PROJECT_NAME
require_mode

if [ "${lan}" = true ] && [ "${MODE}" != development ]; then
    echo "正式環境不能用 lan：nginx 信任上一層送來的 X-Real-IP，對外開放就能冒充任何 IP" >&2
    exit 1
fi
if [ "${lan}" = true ]; then
    export DEV_BIND_ADDRESS=0.0.0.0
else
    export DEV_BIND_ADDRESS=127.0.0.1
fi

# 正式環境先確認停在發版的 tag 上, 檢查的才是要上線的那份模板。
if [ "${MODE}" = production ]; then
    require_release_checkout
fi
check_nginx_config

# compose 要等 migrate 跑完才知道它失敗, 那時線上的 api 已經被換成新的容器而起不來, 結果就是停機。
# 所以先用要上線的 image 單獨跑一次: 失敗就停在這裡, 線上服務維持原狀 (PostgreSQL 的 DDL 在交易裡,
# 失敗會整個撤回)。成功之後 up 裡的 migrate 沒有待執行的 migration, 直接結束。
migrate_first() {
    if ! app_compose run --rm -T "$@" migrate; then
        echo "migration 失敗，沒有切換任何服務（原因見上方訊息）" >&2
        exit 1
    fi
}

if [ "${MODE}" = development ]; then
    migrate_first
    app_compose up -d --remove-orphans
else
    if [ -n "${API_IMAGE:-}${WEB_IMAGE:-}" ]; then
        require_env API_IMAGE WEB_IMAGE
        export IMAGE_PULL_POLICY=always
        migrate_first --pull always
        app_compose up -d --remove-orphans
    else
        migrate_first --build
        app_compose up -d --build --remove-orphans
    fi
fi
echo "已啟動：http://localhost:${SYSTEM_PORT}"
if [ "${lan}" = true ]; then
    print_lan_urls
fi
