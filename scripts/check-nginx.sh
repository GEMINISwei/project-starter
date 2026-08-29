#!/usr/bin/env bash
#
# 確認每個 proxy location 都覆寫了用戶端 IP 標頭，並用 nginx -t 檢查模板語法。
#
# 為什麼要守：後端的限流只讀 `X-Real-IP`（`shared/http/rate_limit.py` 的 `client_ip()`），
# 而且**無條件信任它** —— 正確性完全建立在「nginx 一定會用 $remote_addr 覆寫掉用戶端送來的
# 值」這個前提上。漏掉一個 location block 的後果是：那條路徑上的請求帶著用戶端自己宣稱的
# IP 進到後端，於是所有人共用同一個限流 key（一個人打爆，全站被鎖）——
# 而且**完全靜默**，沒有任何錯誤、日誌或測試會提到它。
#
# 覆寫而不是附加（`$proxy_add_x_forwarded_for`）也是同一個理由：附加會把用戶端送進來的
# 值留在最前面。理由的完整版在 infra/nginx/templates/default.conf.template 的同一段註解。
set -euo pipefail

# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

TEMPLATE_DIR="infra/nginx/templates"

# 不必帶用戶端 IP 標頭的 location。**每條都要附理由**，比照 scripts/check-docs.sh 的 ALLOW
# 與 apps/web/knip.ts 的慣例 —— 沒有理由的例外會變成沒人敢動的永久設定。
ALLOW=(
    # Next 的 HMR WebSocket，dev only。它只連到 dev server 的熱更新通道，
    # 既不會走到後端，也不經過限流。
    "default.dev.conf.template|/_next/hmr"
)

is_allowed() {
    local candidate="$1" allowed
    for allowed in "${ALLOW[@]}"; do
        [ "$candidate" = "$allowed" ] && return 0
    done
    return 1
}

# 輸出每個「有 proxy_pass 的 location」一行：起始行號、名稱、兩個標頭在不在。
locations() {
    awk '
        /^[[:space:]]*location[[:space:]]/ {
            inblock = 1; depth = 0; start = NR
            has_pass = 0; has_real_ip = 0; has_forwarded = 0
            name = $0
            sub(/^[[:space:]]*location[[:space:]]+/, "", name)
            sub(/[[:space:]]*\{.*$/, "", name)
        }
        inblock {
            # 在副本上數括號，不要動到 $0（後面還要比對內容）。
            # `${COMPOSE_PROJECT_NAME}` 這種插值左右括號成對，不影響深度。
            copy = $0
            depth += gsub(/\{/, "{", copy)
            copy = $0
            depth -= gsub(/\}/, "}", copy)
            if ($0 ~ /proxy_pass/) has_pass = 1
            if ($0 ~ /proxy_set_header[[:space:]]+X-Real-IP[[:space:]]+\$remote_addr/) has_real_ip = 1
            if ($0 ~ /proxy_set_header[[:space:]]+X-Forwarded-For[[:space:]]+\$remote_addr/) has_forwarded = 1
            if (depth <= 0) {
                if (has_pass) print start "\t" name "\t" has_real_ip "\t" has_forwarded
                inblock = 0
            }
        }
    ' "$1"
}

failed=0
found=0
for template in "$TEMPLATE_DIR"/*.conf.template; do
    [ -f "$template" ] || continue
    base="$(basename "$template")"
    while IFS=$'\t' read -r lineno name real_ip forwarded; do
        found=$((found + 1))
        is_allowed "$base|$name" && continue
        [ "$real_ip" = "1" ] || {
            echo "$template:$lineno: location $name 有 proxy_pass 但沒有" \
                 "\`proxy_set_header X-Real-IP \$remote_addr\`" >&2
            failed=1
        }
        [ "$forwarded" = "1" ] || {
            echo "$template:$lineno: location $name 有 proxy_pass 但沒有" \
                 "\`proxy_set_header X-Forwarded-For \$remote_addr\`（要覆寫，不是附加）" >&2
            failed=1
        }
    done < <(locations "$template")
done

# 一個 location 都沒掃到，代表 awk 或 glob 壞了。這時候「全部通過」是最危險的結果，
# 所以當成失敗處理（同 check-docs.sh 收不到識別字時的做法）。
[ "$found" -gt 0 ] || { echo "掃不到任何帶 proxy_pass 的 location，檢查器本身壞了" >&2; exit 1; }

if [ "$failed" -ne 0 ]; then
    echo >&2
    echo "限流只讀 X-Real-IP 且無條件信任它 —— 漏一個 location 就是全站共用一個限流 key。" >&2
    exit 1
fi

# ── 語法檢查 ────────────────────────────────────────────────────────────────
#
# 沒有這一步，兩份模板**完全沒有任何檢查**：打錯一個分號，前面所有 job 照樣綠燈，
# 到部署當下 nginx 才 crash-loop（而它是唯一對外的服務，等於整個站起不來）。
#
# 版本跟著 compose 走，不要另外寫死一個 —— 用不同版本驗過的語法不算驗過。
# 模板是 envsubst 的輸入，`${VAR}` 不是合法的 nginx 語法，所以先把變數代換掉再驗；
# 代換用的值只要能讓語法成立就好，不必是真的。
NGINX_IMAGE="$(sed -n 's/^[[:space:]]*image:[[:space:]]*\(nginx:[^[:space:]]*\).*/\1/p' \
    infra/docker/docker-compose.yml | head -1)"
[ -n "${NGINX_IMAGE}" ] || { echo "在 compose 裡找不到 nginx 的 image，檢查器本身壞了" >&2; exit 1; }

if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    echo "nginx 的用戶端 IP 標頭都覆寫了（$found 個）；語法檢查略過（沒有可用的 docker）"
    exit 0
fi

workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT
for template in "$TEMPLATE_DIR"/*.conf.template; do
    base="$(basename "$template" .template)"
    # shellcheck disable=SC2016 # envsubst 的參數是「要代換哪幾個變數」的字面清單，
    # 不是要展開的運算式 —— 不限定的話它會把 nginx 自己的 $host、$remote_addr 也吃掉。
    COMPOSE_PROJECT_NAME=check MODE=development \
        envsubst '${COMPOSE_PROJECT_NAME} ${MODE}' <"$template" >"$workdir/$base"
done

# `nginx -t` 會連 nginx.conf 主檔一起驗，而 conf.d/*.conf 正是它 include 的位置。
docker run --rm -v "$workdir:/etc/nginx/conf.d:ro" "$NGINX_IMAGE" nginx -t >/dev/null 2>&1 || {
    echo "nginx 設定語法錯誤：" >&2
    docker run --rm -v "$workdir:/etc/nginx/conf.d:ro" "$NGINX_IMAGE" nginx -t >&2 || true
    exit 1
}

echo "nginx 的用戶端 IP 標頭都覆寫了（$found 個），兩份設定的語法也通過（${NGINX_IMAGE}）"
