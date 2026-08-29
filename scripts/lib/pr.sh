#!/usr/bin/env bash
#
# 取得「目前這個 PR」的標題與描述，給需要讀它們的檢查器共用
# （check-acceptance、check-test-edits）。
#
# 兩條來源刻意共用同一份取得邏輯：CI 由 env 餵進來，本機用 gh 取當前分支的 PR。
# 各寫一份的話「本機跑過」就不代表 CI 會過 —— 而這兩支的判斷完全建立在這兩個字串上。
#
# **CI 一律經 env 傳，不可內插進 run 的腳本字串**：PR 標題與描述是任何人都能編輯的內容，
# 內插等於讓 PR 作者在 runner 上執行任意指令。ci.yml 的 changelog job 同理。
#
# 被 source，所以刻意不設 `set -euo pipefail` —— 那是呼叫端的決定，同 common.sh。

# shellcheck source=scripts/lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

[ -n "${PR_SH_LOADED:-}" ] && return 0
PR_SH_LOADED=1

# 填好 PR_TITLE 與 PR_BODY。讀不到 PR 就回傳 1，**要跳過還是要失敗由呼叫端決定** ——
# 目前兩個呼叫端都是跳過：還沒開 draft PR 就跑檢查器不該失敗。
pr_context() {
    PR_TITLE="${PR_TITLE:-}"
    PR_BODY="${PR_BODY:-}"

    if [ -z "$PR_BODY" ]; then
        command -v gh > /dev/null 2>&1 || return 1
        PR_BODY="$(gh pr view --json body -q .body 2> /dev/null)" || return 1
        PR_TITLE="$(gh pr view --json title -q .title 2> /dev/null || true)"
    fi

    # GitHub 的 PR 描述是 CRLF。不先剝掉的話 `$0 == "## 某節"` 這種比對永遠對不上，
    # 而症狀是「抽不到內容」—— 看起來像作者沒寫，實際上是換行符。
    PR_BODY="$(tr -d '\r' <<< "$PR_BODY")"
    export PR_TITLE PR_BODY
}

# PR 標題帶著某個放行標記就回傳 0。放行一律要**明講**，不靠某個條件預設放行 ——
# 比照 ci.yml 的 changelog job 的 [skip changelog]。
pr_skipped() {
    case "$PR_TITLE" in
        *"[$1]"*) return 0 ;;
        *) return 1 ;;
    esac
}
