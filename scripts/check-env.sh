#!/usr/bin/env bash
#
# 確認環境變數的四個同步點沒有各自飄。
#
# 為什麼需要這個：`.env.example` 是清單、`init.sh` 決定新專案實際拿到什麼、compose 負責注入、
# `app/config.py` 決定後端讀得到什麼 —— 四處都是手寫的，而且**沒有任何程式讀 `.env.example`**。
# 典型的錯法（「清單寫 1、init.sh 產生 8」、「清單說可留空、compose 卻是 `${VAR:?}`」）不會讓
# 任何指令失敗，只會讓照著清單設定的人踩坑。
set -euo pipefail

# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

readonly EXAMPLE=".env.example"
readonly INIT="scripts/init.sh"
readonly CONFIG="apps/api/app/config.py"
COMPOSE_FILES=(infra/docker/docker-compose.yml infra/docker/docker-compose.dev.yml infra/docker/docker-compose.prod.yml)

# compose 會引用、但不該出現在 .env 的變數。`MODE` 由 dev.sh／prod.sh 決定，
# 使用者不設也不該設（`.env.example` 的檔頭有寫）。
#
# `API_IMAGE`／`WEB_IMAGE`／`IMAGE_PULL_POLICY` 同理，由 deploy.sh 匯出：
# 它們是「這次部署用哪個 tag」這個一次性參數的載體，寫進 .env 就會變成過期狀態。
readonly COMPOSE_INTERNAL="MODE API_IMAGE WEB_IMAGE IMAGE_PULL_POLICY"

# `.env.example` 有、但 compose 用不到的變數（只給主機端腳本或建置流程用的）。
# 這一欄短才是常態，長長一串代表 .env 開始承擔它不該承擔的東西。
#
# `IMAGE_REGISTRY`／`IMAGE_TAG` 只有 scripts/deploy.sh 讀，讀完組成上面那三個
# compose 變數。容器裡沒有任何東西需要知道自己是從哪個 registry 來的。
readonly HOST_ONLY="IMAGE_REGISTRY IMAGE_TAG"

# `AppEnv` 有欄位、但刻意不由環境變數指定的。`jwt_algorithm` 直接餵給 jwt.encode/decode，
# 型別是 `Literal["HS256"]` —— 開放給部署端設定只會多一個「設了看起來有效、其實只有一個值
# 能通過」的旋鈕（見 config.py 該欄位的註解）。
readonly CONFIG_ONLY="JWT_ALGORITHM"

# 這幾個在 `.env.example` 裡必須保持空值。那份檔案會隨模板散播到每個下游專案，
# 填了值等於把祕密一起送出去，而且下游多半不會察覺自己用的是別人的金鑰。
readonly SECRETS="POSTGRES_PASSWORD JWT_SECRET_KEY REGISTER_KEY
                  NEXT_SERVER_ACTIONS_ENCRYPTION_KEY VAPID_PRIVATE_KEY VAPID_PUBLIC_KEY"

fail=0
# 第一個參數是標題，其餘每個參數各印一行。
#
# 呼叫端**刻意**把變數不加引號傳進來（`report "標題：" $missing`）：那些變數裝的是
# 換行分隔的 key 清單，靠 word splitting 拆成一個參數一個 key 才會一行一個。加了引號
# 會變成整包擠在一行、而且前面多兩個空白。所以底下每個呼叫點都關掉 SC2086。
report() {
    fail=1
    echo "$1" >&2
    shift
    printf '  %s\n' "$@" >&2
}

# 行首的 `KEY=`。init.sh 只有 heredoc 那一段是這個形狀（腳本自己的變數都是小寫），
# 所以整份檔案抓下去就是它寫進 .env 的完整清單。
keys_of() { grep -oE '^[A-Z_][A-Z0-9_]*=' "$1" | tr -d '=' | sort -u; }

# 取某個 key 的值，去掉行內註解與頭尾空白。
value_of() {
    local raw
    raw="$(grep -m1 -E "^$2=" "$1" | cut -d= -f2-)"
    raw="${raw%%#*}"
    printf '%s' "$raw" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
}

# compose 插值引用的變數。先濾掉整行註解（檔案裡有一行註解在講 `${VAR:?}` 這個寫法），
# 再把 `$$` 換掉 —— `$${POSTGRES_USER}` 是留給容器內 shell 的（healthcheck），
# 不是 compose 要插值的東西，不濾掉會被誤認成缺少的變數。
compose_refs() {
    cat "${COMPOSE_FILES[@]}" \
        | grep -v '^[[:space:]]*#' \
        | sed 's/\$\$/@@/g' \
        | grep -oE '\$\{[A-Za-z_][A-Za-z0-9_]*' \
        | sed 's/^\${//' | sort -u
}

# `AppEnv` 的欄位名（小寫）轉成環境變數名（大寫）。config.py 的 alias_generator 就是
# `lambda x: x.upper()`，所以這個轉換不是猜的。
#
# 只抓 class 主體裡縮排四格的 `欄位: 型別`，遇到縮排回到頂層（下一個 def／class）就停 ——
# 檔案裡其他地方也有 `名稱:` 形狀的東西（型別註記、dict），整份抓會混進來。
config_keys() {
    awk '
        /^class AppEnv/ { inside = 1; next }
        inside && /^[^[:space:]]/ { inside = 0 }
        inside && /^    [a-z_][a-z0-9_]*:/ {
            sub(/:.*/, ""); gsub(/ /, ""); print toupper($0)
        }
    ' "$CONFIG" | sort -u
}

# compose 實際注入給某個 service 的環境變數名。
#
# 只看 `api`：它是唯一載入 `app/config.py` 的服務。`migrate` 跑的 `scripts/db.py` 刻意
# 直接讀 `os.environ`（只要三個變數），沒有經過 AppEnv —— 拿同一組規則去對它會要求它
# 帶上 JWT_SECRET_KEY 之類根本用不到的東西。
service_env_keys() {
    awk -v want="$1" '
        /^  [a-z][a-z0-9_-]*:/ { in_service = ($0 == "  " want ":"); in_env = 0 }
        in_service && /^    environment:/ { in_env = 1; next }
        in_env && /^    [a-zA-Z]/ { in_env = 0 }
        in_env && /^      [A-Z_][A-Z0-9_]*:/ { sub(/:.*/, ""); gsub(/ /, ""); print }
    ' infra/docker/docker-compose.yml | sort -u
}

for f in "$EXAMPLE" "$INIT" "$CONFIG" "${COMPOSE_FILES[@]}"; do
    test -f "$f" || { echo "找不到 $f" >&2; exit 1; }
done

example_keys="$(keys_of "$EXAMPLE")"
init_keys="$(keys_of "$INIT")"

# ── 1. .env.example 與 init.sh 的變數集合要一致 ──────────────────────────────
# 清單有、init.sh 沒產生：新專案跑完 make init 就少一個變數，服務可能起不來。
# init.sh 有、清單沒列：使用者看不到這個變數存在。兩個方向都是錯。
missing_in_init="$(comm -23 <(echo "$example_keys") <(echo "$init_keys"))"
missing_in_example="$(comm -13 <(echo "$example_keys") <(echo "$init_keys"))"

# shellcheck disable=SC2086 # 見 report() 的呼叫慣例
[ -z "$missing_in_init" ] || report \
    "$EXAMPLE 有、但 $INIT 不會寫進 .env：" $missing_in_init
# shellcheck disable=SC2086 # 同上
[ -z "$missing_in_example" ] || report \
    "$INIT 會寫進 .env、但 $EXAMPLE 沒列出來：" $missing_in_example

# ── 2. 共同的字面預設值要一致 ────────────────────────────────────────────────
# 只比對兩邊都是字面值的欄位：init.sh 用 shell 變數的（互動輸入或 openssl 產生）
# 本來就沒有固定值，example 空著的是祕密欄位。
for key in $(comm -12 <(echo "$example_keys") <(echo "$init_keys")); do
    ev="$(value_of "$EXAMPLE" "$key")"
    iv="$(value_of "$INIT" "$key")"
    case "$iv" in ''|*'$'*) continue ;; esac
    [ -n "$ev" ] || continue
    [ "$ev" = "$iv" ] || report \
        "$key 的預設值不一致：" "$EXAMPLE = $ev" "$INIT = $iv"
done

# ── 3. compose 引用的變數要在清單裡 ──────────────────────────────────────────
refs="$(compose_refs)"
# 這兩個 allowlist 在上面是空白分隔的字串，同樣要靠 word splitting 才會一行一個。
# shellcheck disable=SC2086
allow_compose="$(printf '%s\n' $COMPOSE_INTERNAL | sort -u)"
# shellcheck disable=SC2086
allow_host="$(printf '%s\n' $HOST_ONLY | sort -u)"

undeclared="$(comm -13 <(echo "$example_keys") <(comm -23 <(echo "$refs") <(echo "$allow_compose")))"
unused="$(comm -23 <(comm -23 <(echo "$example_keys") <(echo "$refs")) <(echo "$allow_host"))"

# shellcheck disable=SC2086 # 見 report() 的呼叫慣例
[ -z "$undeclared" ] || report \
    "compose 引用了 $EXAMPLE 沒列出的變數：" $undeclared
# shellcheck disable=SC2086 # 同上
[ -z "$unused" ] || report \
    "$EXAMPLE 列了 compose 用不到的變數（只給主機端用的話請加進本腳本的 HOST_ONLY）：" $unused

# ── 4. .env.example 裡的祕密欄位必須是空的 ───────────────────────────────────
for key in $SECRETS; do
    v="$(value_of "$EXAMPLE" "$key")"
    [ -z "$v" ] || report \
        "$EXAMPLE 的 $key 有值 —— 這份檔案會隨模板散播，祕密欄位必須留空：" "$key=$v"
done

# ── 4b. init.sh 必須真的產生每一個祕密 ───────────────────────────────────────
#
# 這是第 4 條的反面，而少了它整組檢查是半殘的：`.env.example` 留空**是規定**，
# 所以「留空」不能當成「有人會填」的證據 —— 真正會填的是 `init.sh`。
# 而第 3 條的預設值比對遇到空值就 `continue`（那是為了放行 `$` 展開），
# 於是把 `init.sh` 的 `JWT_SECRET_KEY=` 清空之後，前面每一條都會照樣通過。
#
# 後果不是「少一個變數」：服務會照常啟動，只是簽出來的 token 任何人都能偽造
# （`.env.example` 那個欄位的註解講的就是這件事）。
for key in $SECRETS; do
    v="$(value_of "$INIT" "$key")"
    case "$v" in
        *'$'*) ;;  # 由 shell 變數展開 —— 這正是預期的寫法
        *) report "$INIT 沒有真的產生 ${key}（值是 \"$v\"）——" \
               "祕密欄位在 $EXAMPLE 留空是規定，所以只有這裡會填它" ;;
    esac
done

# ── 5. app/config.py 讀的變數與 compose 注入給 api 的要一致 ──────────────────
# 第四個同步點，也是最安靜的一個：兩個方向的錯都不會讓任何指令失敗。
#   - AppEnv 有欄位、compose 沒注入：那個欄位永遠是預設值，沒有人會發現 .env 設的值沒生效。
#   - compose 注入了 AppEnv 沒有的欄位：pydantic-settings 直接忽略，設定的人卻以為開了功能。
config_keys="$(config_keys)"
api_env_keys="$(service_env_keys api)"
# shellcheck disable=SC2086 # 見 report() 的呼叫慣例
allow_config_only="$(printf '%s\n' $CONFIG_ONLY | sort -u)"

not_injected="$(comm -23 <(echo "$config_keys") <(cat <(echo "$api_env_keys") <(echo "$allow_config_only") | sort -u))"
not_read="$(comm -13 <(echo "$config_keys") <(echo "$api_env_keys"))"

# shellcheck disable=SC2086 # 見 report() 的呼叫慣例
[ -z "$not_injected" ] || report \
    "$CONFIG 讀得到、但 compose 沒有注入給 api（會一直是預設值）：" $not_injected
# shellcheck disable=SC2086 # 同上
[ -z "$not_read" ] || report \
    "compose 注入給 api、但 $CONFIG 沒有對應欄位（會被忽略）：" $not_read

[ "$fail" -eq 0 ] || exit 1
# ${} 不可省：後面緊接全形斜線時，bash 會把那幾個 byte 一起吃進變數名。
echo "環境變數四處一致（${EXAMPLE}／${INIT}／compose／${CONFIG}）"
