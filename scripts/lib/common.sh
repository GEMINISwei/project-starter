#!/usr/bin/env bash
#
# 所有 scripts/*.sh 共用的基礎: repo 根定位、.env 載入、互動確認、契約路徑。
#
# 這支是被 source 的, 所以刻意**不**寫 `set -euo pipefail` —— 那是呼叫端的決定,
# 由被 source 的檔案偷偷改變呼叫端的 shell 行為很難追。

# 重複 source 的保護。compose.sh 會 source 這一支, 腳本自己再 source 一次是很自然的寫法,
# 而下面的 readonly 被賦值第二次會直接讓 `set -e` 的呼叫端中止。
[ -n "${COMMON_SH_LOADED:-}" ] && return 0
COMMON_SH_LOADED=1

# 一律解析成絕對路徑再 cd 過去, 讓每支腳本從任何 CWD 都能跑 (`make -C /path/to/repo dev`、
# 編輯器的 task、CI 都算)。用 ${BASH_SOURCE[0]} 而不是 $0: $0 是呼叫端腳本的路徑,
# 被 source 的這一支往上兩層才是 repo 根。
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly REPO_ROOT
# cd 失敗代表 repo 根算錯了, 之後每一條相對路徑都會指到別的地方 —— 而那正是最難查的錯。
# 被 source 的檔案裡 `exit` 會結束呼叫端腳本, 這裡要的就是那個行為。
cd "$REPO_ROOT" || exit 1

# 契約與它的 TypeScript 投影。這兩個路徑**只在這裡定義一份** (`make gen-types` 取用)。
# shellcheck disable=SC2034 # 給 source 這支的腳本用 (gen-types.sh)
readonly CONTRACT="contracts/openapi.json"
# shellcheck disable=SC2034 # 同上
readonly WEB_SCHEMA="apps/web/shared/api/generated/schema.d.ts"

# 載入 repo 根的 .env。**不存在不算錯誤**: lint/build 那類主機端指令在還沒跑過
# make init 的機器上也該能跑。
# 真的需要某個變數的腳本請接著呼叫 require_env。
#
# **為什麼是自己 parse, 不是 `set -a; . .env`**:.env 不是 shell 腳本。`SYSTEM_NAME=My App`
# (init.sh 的預設值就長這樣) source 下去會變成執行 `App` 這個指令, 訊息是 `App: command not
# found`, 完全看不出跟 .env 有關; `POSTGRES_PASSWORD=  # 必填` 的行內註解也會被當成值。
#
# 規則對齊 `docker compose --env-file` 對同一份檔案的解讀 (compose 也直接讀這份, 不一致的話同一
# 個變數在 shell 與容器裡會是不同的值): 全行註解與空行略過、以第一個 `=` 切開、成對引號剝掉、
# 未加引號的值從第一個「空白 + #」起算行內註解並去掉頭尾空白。
load_env() {
    if [ -f "$REPO_ROOT/.env" ]; then
        local line key value trimmed
        while IFS= read -r line || [ -n "$line" ]; do
            case "$line" in
                ''|'#'*) continue ;;
                *=*) ;;
                *) continue ;;
            esac

            key="${line%%=*}"
            key="${key#"${key%%[![:space:]]*}"}"
            key="${key%"${key##*[![:space:]]}"}"
            key="${key#export }"
            # 不是合法的變數名就跳過, 不要讓一行怪東西弄壞整份載入。
            case "$key" in ''|*[!A-Za-z0-9_]*) continue ;; esac

            value="${line#*=}"
            trimmed="${value#"${value%%[![:space:]]*}"}"
            case "$trimmed" in
                '"'*'"') value="${trimmed%\"}"; value="${value#\"}" ;;
                "'"*"'") value="${trimmed%\'}"; value="${value#\'}" ;;
                *)
                    # 先去前導空白再找行內註解, 順序不能反 —— compose 就是這樣做的:
                    # `K=   # x` 去掉前導空白後 `#` 貼在最前面, 不算行內註解 (那需要前面有空白),
                    # 整串 `# x` 就是值。先找註解的話會誤判成空值。
                    value="${trimmed%%[[:space:]]#*}"
                    value="${value%"${value##*[![:space:]]}"}"
                    ;;
            esac

            export "$key=$value"
        done < "$REPO_ROOT/.env"
    fi
    # 先載 .env 再套預設值, 所以 .env 裡的設定優先。
    : "${SYSTEM_PORT:=3000}"
    export SYSTEM_PORT
}

# 缺少必要的環境變數就中止。碰 docker 的腳本用, 避免把空字串接進容器名稱
# (`-api` 這種名字會 match 不到任何容器, 錯誤訊息卻完全看不出原因)。
require_env() {
    local missing="" name
    for name in "$@"; do
        [ -n "${!name:-}" ] || missing="$missing $name"
    done
    if [ -n "$missing" ]; then
        # ${} 不可省: 後面緊接全形括號時, bash 會把那幾個 byte 一起吃進變數名。
        echo "缺少環境變數：${missing}（請確認 .env，或先執行 make init dev|prod）" >&2
        exit 1
    fi
}

# .env 的 MODE 決定這台主機是哪種環境: compose 疊哪份 overlay、volume 叫什麼、哪些指令不能跑。
# 只由 `make init dev|prod` 寫入。缺少或值不對時停下來, 不猜: 猜錯就是用另一組 volume 起服務,
# 或在正式主機上放行開發用的指令。
require_mode() {
    case "${MODE:-}" in
        production|development) ;;
        *)
            echo ".env 的 MODE 必須是 production 或 development（目前是「${MODE:-}」）：" >&2
            echo "  刪掉 .env 重跑 make init dev|prod，或手動補上 MODE=…" >&2
            exit 1
            ;;
    esac
}

# 用法: deny_on_production <指令>
#
# 只屬於開發機的指令 (清空資料、產生 migration、檢查與發版) 在正式主機上拒絕執行。
# 沒有 MODE 時放行: CI 沒有 .env, 而 `make check` 要在那裡跑。
# 這是防手誤, 不是權限控制 —— 能上主機的人照樣可以改 .env。
deny_on_production() {
    if [ "${MODE:-}" = production ]; then
        echo "正式環境（MODE=production）不能執行 $1" >&2
        exit 1
    fi
}

# 這份 checkout 的版號 (`apps/api/app/config.py` 的 APP_VERSION, 不帶 v)。
# 部署主機 checkout 的就是正在跑的 tag, 所以在主機上這也是線上的版本。
app_version() {
    local version
    version="$(sed -n 's/^APP_VERSION = "\(.*\)"$/\1/p' "$REPO_ROOT/apps/api/app/config.py")"
    if [ -z "$version" ]; then
        echo "在 apps/api/app/config.py 找不到 APP_VERSION" >&2
        return 1
    fi
    printf '%s\n' "$version"
}

# 破壞性操作前的 y/N 確認。
confirm() {
    local ans=""
    printf '%s [y/N] ' "$1"
    # 讀不到輸入 (stdin 不是終端機, 例如經過 ssh 的腳本) 算取消, 也要印出原因。
    read -r ans || true
    if [ "$ans" != "y" ] && [ "$ans" != "Y" ]; then
        echo "已取消"
        exit 1
    fi
}
