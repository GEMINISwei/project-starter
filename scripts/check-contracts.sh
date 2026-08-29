#!/usr/bin/env bash
#
# 確認契約產出物有沒有真的落在該落的地方（gen-types 跑完會自動叫它一次）。
#
# `$CONTRACT` 打錯檔名時 gen-types 仍可能成功，`api-types-up-to-date` job 也看不到落在別處的產出物。
#
# 檢查方式是抓「未被追蹤的產出物」：正確的兩份都是 committed 的，所以路徑解錯後掉出來的
# 副本一定是未進版控的檔案。兩種找法都需要，因為打錯的方式不只一種：
#   - 目錄打對、檔名打錯（contracts/openapi.jsn）→ 靠「這兩個目錄裡不該有未追蹤的檔案」抓
#   - 檔名打對、落到別的目錄（apps/api/openapi.json）→ 靠檔名比對抓
set -euo pipefail

# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

# ${} 不可省：後面緊接全形逗號時，bash 會把那幾個 byte 一起吃進變數名。
test -f "$CONTRACT"   || { echo "找不到契約 ${CONTRACT}，請檢查 scripts/lib/common.sh 的 CONTRACT" >&2; exit 1; }
test -f "$WEB_SCHEMA" || { echo "找不到型別檔 ${WEB_SCHEMA}，請檢查 scripts/lib/common.sh 的 WEB_SCHEMA" >&2; exit 1; }

# 未追蹤檔案的比對需要 git。模板本身在 make init 之前沒有 .git，這時能檢查的就只有上面
# 那兩個 test -f —— 直接讓 git 噴錯只會蓋掉真正的訊息。
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "契約路徑正確（非 git repo，略過未追蹤產出物檢查）"
    exit 0
fi

stray="$( {
    git ls-files --others --exclude-standard -- "$(dirname "$CONTRACT")" "$(dirname "$WEB_SCHEMA")"
    git ls-files --others --exclude-standard \
        | grep -E "(^|/)($(basename "$CONTRACT")|$(basename "$WEB_SCHEMA"))$" || true
} | sort -u )"

if [ -n "$stray" ]; then
    echo "產出物落在非預期的位置：" >&2
    printf '%s\n' "$stray" | sed 's/^/  /' >&2
    echo "請檢查 scripts/lib/common.sh 的 CONTRACT／WEB_SCHEMA" >&2
    exit 1
fi

echo "契約路徑正確"
