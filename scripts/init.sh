#!/usr/bin/env bash
#
# 開案: 確認 docker 與專案名稱可用、產生 .env、安裝主機端相依、建立 git 歷史。
#
#   make init       可以重跑: 已有的 .env 與 .git 會跳過, 相依會照 lock 檔重新安裝
#   make init env   只產生 .env (部署主機用: 那裡只跑容器, 不必裝 uv 與 Node)
#
# 服務跑在容器裡 (`make dev`), 但 `make check` 在主機上跑 —— 那才是編輯器與 CI 看到的
# 環境, 所以開發機要把 uv 與 npm 的相依裝好。
#
# 產生的祕密一律用 openssl, 不用 $RANDOM 那類 —— 這些值直接決定 JWT 與 Server Action 的
# 簽章強度。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

usage() {
    sed -n '/^#   make init/s/^#   //p' "$0" >&2
    exit 1
}

require_tools() {
    local missing="" tool
    for tool in "$@"; do
        command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
    done
    if [ -n "$missing" ]; then
        echo "缺少必要工具：$missing" >&2
        echo "docker 見 https://docs.docker.com/get-docker/ ；uv 見 https://docs.astral.sh/uv/ ；node 與 npm 一起安裝。" >&2
        exit 1
    fi
}

# Node 要落在正確的 major 且不低於下限。**兩個數字來自兩份檔案**, 各自只有一個意思:
# major 線在 apps/web/.nvmrc (nvm 與 CI 的 setup-node 讀它; Dockerfile 讀不到,
# 它的 ARG NODE_VERSION 是要手動跟上的第三處),
# 下限在 package.json 的 engines。理由見那份檔案的 `//engines`。
#
# 為什麼把關放在這裡而不是靠 npm 的 engines 檢查: npm 預設只印一行 EBADENGINE
# warning 就繼續裝, 而 `engine-strict=true` 會**連帶檢查每個相依套件宣告的 engines**,
# 任何一個第三方套件寫窄了都會擋住安裝 —— 誤傷面太大。這裡只管我們自己訂的那條線。
check_node_version() {
    local required_major required_min current_node current_version lowest
    required_major="$(tr -d '[:space:]' < apps/web/.nvmrc)"
    required_min="$(node -p "require('./apps/web/package.json').engines.node.match(/\d+\.\d+\.\d+/)[0]")"
    current_node="$(node -v)"
    current_version="${current_node#v}"

    # 用 sort -V 比版本, 不要自己拆 major/minor/patch 再用 `[ -gt ]`:.nvmrc 只寫 major
    # (下游改它是預期行為) 時拆出來的欄位是空字串, `[ "$x" -gt "" ]` 會變成
    # `unary operator expected` —— 結果是用著合法的 Node 卻被擋下, 訊息還看不出原因。
    lowest="$(printf '%s\n%s\n' "$required_min" "$current_version" | sort -V | head -1)"
    if [ "${current_version%%.*}" != "$required_major" ] || [ "$lowest" != "$required_min" ]; then
        echo "Node 版本不符：需要 >=v${required_min} 且 major 為 ${required_major}，目前是 ${current_node}" >&2
        echo "用 nvm 的話：nvm use \"$(cat apps/web/.nvmrc)\"" >&2
        exit 1
    fi
}

# 改寫 .env 裡既有的 `KEY=` 那一行。值經環境變數傳進 awk, 不經 sed 的取代字串:
# base64 的 `/`、`+` 與系統名稱裡的空白都不必跳脫。
#
# key 不在範本裡就中止 —— 那代表 .env.example 少了一項, 安靜地略過的話 .env 會缺變數,
# 症狀要到 compose 的 `:?` 才出現。
set_env_value() {
    local file="$1" key="$2" value="$3"
    grep -q "^${key}=" "$file" || { echo "內部錯誤：.env.example 沒有 ${key}" >&2; exit 1; }
    KEY="$key" VALUE="$value" awk '
        index($0, ENVIRON["KEY"] "=") == 1 { print ENVIRON["KEY"] "=" ENVIRON["VALUE"]; next }
        { print }
    ' "$file" > "$file.tmp"
    mv "$file.tmp" "$file"
}

prompt_until_valid() {
    local __var="$1" label="$2" default="$3" validator="$4" answer
    while :; do
        if [ -n "$default" ]; then printf '%s [%s]: ' "$label" "$default"; else printf '%s：' "$label"; fi
        read -r answer
        answer="${answer:-$default}"
        if "$validator" "$answer"; then
            printf -v "$__var" '%s' "$answer"
            return
        fi
    done
}

valid_project_name() {
    case "$1" in
        ''|[!a-z0-9]*|*[!a-z0-9_-]*)
            echo "專案名稱須以小寫英文字母或數字開頭，且只能包含小寫英文字母、數字、-、_"
            return 1 ;;
    esac
}

valid_system_name() {
    case "$1" in
        *\'*) echo "系統名稱不可包含單引號"; return 1 ;;
    esac
}

valid_port() {
    case "$1" in
        *[!0-9]*|'') ;;
        *) [ "$1" -ge 1 ] && [ "$1" -le 65535 ] && return 0 ;;
    esac
    echo "Port 必須是 1 到 65535 的整數"
    return 1
}

valid_db_user() {
    case "$1" in
        ''|*[!A-Za-z0-9._~-]*) echo "資料庫帳號只能包含英文字母、數字、.、_、~、-"; return 1 ;;
    esac
}

# 字元集限制不是美觀問題: 這個值會被插進 compose 的 `postgresql+asyncpg://user:pass@host/db`,
# 而 `@`、`:`、`/` 之類的字元會把那個 URL 切在錯的地方 —— 症狀是「認證失敗」,
# 看不出跟密碼裡的字元有關。
valid_db_password() {
    case "$1" in
        ''|*[!A-Za-z0-9._~-]*)
            echo "資料庫密碼不可為空，且只能包含英文字母、數字、.、_、~、-"
            return 1 ;;
    esac
}

# 以 .env.example 為範本, 只改問到的與自動產生的那幾項 —— 其餘預設值與註解都直接沿用,
# 新增一個有預設值的變數時不必動這支腳本。
create_env() {
    if [ -f .env ]; then
        echo ".env 已存在，跳過"
        return
    fi

    local project_name system_name system_port db_user db_password
    printf '請輸入初始化資訊\n'
    prompt_until_valid project_name "專案名稱" "my-app" valid_project_name
    # 一問到就查, 不必等其他問題都答完才發現要重來。
    require_unused_project_name "$project_name"
    prompt_until_valid system_name "系統名稱" "My App" valid_system_name
    prompt_until_valid system_port "系統 Port" "3000" valid_port
    prompt_until_valid db_user "資料庫帳號" "admin" valid_db_user
    prompt_until_valid db_password "資料庫密碼（必填）" "" valid_db_password

    # 先在暫存檔上改完再改名: 中途被 Ctrl-C 時不會留下一份半套的 .env
    # (下次重跑會被「已存在」跳過, 問題就藏起來了)。
    local draft=.env.partial
    trap 'rm -f .env.partial .env.partial.tmp' EXIT
    cp .env.example "$draft"
    set_env_value "$draft" COMPOSE_PROJECT_NAME "$project_name"
    set_env_value "$draft" SYSTEM_NAME "$system_name"
    set_env_value "$draft" SYSTEM_PORT "$system_port"
    set_env_value "$draft" POSTGRES_USER "$db_user"
    set_env_value "$draft" POSTGRES_PASSWORD "$db_password"
    # 資料庫名稱跟著專案名走, 不另外問 —— 一個 compose 專案就是一個資料庫。
    set_env_value "$draft" POSTGRES_DB "$project_name"
    set_env_value "$draft" JWT_SECRET_KEY "$(openssl rand -hex 32)"
    set_env_value "$draft" REGISTER_KEY "$(openssl rand -hex 32)"
    set_env_value "$draft" NEXT_SERVER_ACTIONS_ENCRYPTION_KEY "$(openssl rand -base64 32)"
    mv "$draft" .env
    trap - EXIT

    echo ".env 已依輸入設定建立"
}

install_deps() {
    echo "── apps/api：uv sync ──────────────────────────────────────────────────────"
    # --frozen: 照 uv.lock 裝, 不要順手更新它。相依要升版請明確跑 `uv lock`,
    # 否則「跑一次 init 就默默改了 lock 檔」會在別人的 PR 裡冒出來。
    (cd apps/api && uv sync --frozen)

    echo "── apps/web：npm ci ───────────────────────────────────────────────────────"
    # npm ci 而不是 npm install, 理由同上: ci 嚴格照 package-lock.json 裝, 對不上就報錯。
    (cd apps/web && npm ci)
}

init_git() {
    if [ -e .git ]; then
        echo "Git 已初始化，跳過"
    else
        git init -q -b main
        git add .
        git commit -q -m "initial commit"
        # 走到這一支代表不是 clone 來的 (clone 會帶著 .git)。這個模板是快照式的,
        # 全新歷史正是預期結果, 所以這裡只是說明, 不是警告。
        echo "已建立全新的 git 歷史"
    fi

    # 這裡刻意不問遠端網址: 本機開發測試常常不想綁任何儲存庫, 而這一步跑完就該能 make dev。
    # 正常開案 ("Use this template" 之後 git clone) origin 早就綁好了, 看不到這兩行。
    if ! git remote | grep -q .; then
        echo "尚未綁定任何 git remote。需要的話："
        echo "    git remote add origin <你的 repo 網址> && git push -u origin main"
    fi
}

print_register_key() {
    local register_key
    register_key="$(sed -n 's/^REGISTER_KEY=//p' .env)"
    if [ -n "$register_key" ]; then
        echo "註冊代碼（首次於 /signup 建立超級管理者用）：$register_key"
    else
        echo "註冊代碼已清空，請用 make db superuser 建立超級管理者"
    fi
}

case "${1:-all}" in
    all)
        require_tools openssl uv node npm docker
        require_compose
        check_node_version
        create_env
        install_deps
        init_git
        print_register_key
        echo
        echo "完成。接著："
        echo "  make dev     # 啟動開發環境（首次建置 image 約 2–5 分鐘）"
        echo "  make check   # 送出前的檢查"
        ;;
    env)
        require_tools openssl docker
        require_compose
        create_env
        print_register_key
        ;;
    *) usage ;;
esac
