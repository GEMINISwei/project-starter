#!/usr/bin/env bash
#
# 前後端契約的產生與比對: `make gen-types` 寫進 repo, `make check contract` 與 `make release`
# 只比對。契約與型別檔的路徑定義在 common.sh。
#
# 被 source 的檔案, 理由同 common.sh 不寫 `set -euo pipefail`。

[ -n "${CONTRACT_SH_LOADED:-}" ] && return 0
CONTRACT_SH_LOADED=1

# shellcheck source=scripts/lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# 由後端 OpenAPI 產生契約與它的 TypeScript 投影 (不需啟動服務), 寫到指定的兩個絕對路徑。
# 兩行各自 cd 進不同的 app, 相對路徑在兩行裡會指到不同地方。
# 用 && 串起來: 呼叫端在 `if` 裡呼叫時 `set -e` 不生效, 失敗也要傳得出去。
generate_contract() {
    local contract="$1" schema="$2"
    (cd "$REPO_ROOT/apps/api" && uv run python scripts/export_openapi.py "$contract") \
        && (cd "$REPO_ROOT/apps/web" && npx openapi-typescript "$contract" -o "$schema")
}

# 重新產生到暫存目錄, 再跟 repo 裡的兩份比對: 只讀, 不動工作目錄。
# 比對的是工作目錄裡的檔案, 不是 git 裡的版本, 所以還沒 commit 的 make gen-types 結果也算數。
#
# 整個函式在 subshell 裡跑 (`( )` 而不是 `{ }`): EXIT trap 只管這裡的暫存目錄,
# 不會蓋掉呼叫端自己設的 trap (check.sh 的 integration 也用 EXIT trap 清容器)。
check_contract() (
    tmp="$(mktemp -d)"
    trap 'rm -rf "${tmp}"' EXIT
    if ! generate_contract "${tmp}/openapi.json" "${tmp}/schema.d.ts" > /dev/null; then
        echo "產生契約失敗（見上方訊息）" >&2
        exit 2
    fi
    if ! diff -u "$REPO_ROOT/$CONTRACT" "${tmp}/openapi.json" \
        || ! diff -u "$REPO_ROOT/$WEB_SCHEMA" "${tmp}/schema.d.ts"; then
        echo "契約或前端型別不是最新的：跑 make gen-types，並把兩份產出一起 commit" >&2
        exit 1
    fi
)
