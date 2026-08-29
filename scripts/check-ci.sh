#!/usr/bin/env bash
#
# 確認 CI、本機的 check 腳本與分支保護三者沒有各自漂移。
#
# 守兩件事：
#
#   1. `.github/workflows/ci.yml` 真的跑到 lint／typecheck／test／build 四支腳本裡的每一條指令。
#   2. `.github/rulesets/main.json`（**選配**）要求的 status check，恰好是 ci.yml 裡
#      所有會在 PR 上跑的 job。檔案不在就跳過這一半 —— 見底下。
#
# 為什麼 CI 不乾脆直接呼叫 `make lint` 那幾個 target（那樣就沒有第 1 件事要守了）：
# 那幾支腳本一支同時跑前後端兩邊，而 CI 刻意把 api 與 web 切成兩個平行 job ——
# 直接呼叫會把兩邊串成一條，PR 的等待時間大約翻倍。所以 CI 內嵌等價指令是**刻意**的，
# 代價就是「同一條指令寫在兩個地方」，由這支腳本補起來。
# （附帶一提，`load_env` 在沒有 `.env` 時是 no-op，所以「CI 不能呼叫 make」並不成立，
# 平行切分才是真正的理由。）
#
# 第 2 件事守的是**分支保護**，而它是選配的：ruleset 與舊版 branch protection 對 private
# repo 都要 GitHub Pro（免費方案連 API 都回 403），所以這個模板不預設它存在 ——
# 免費私有專案靠 .githooks/pre-push 與 ci.yml 的 pushed-via-pr job 那兩層。
# `.github/rulesets/main.json` 不在就跳過，不算失敗。
#
# 檔案在的時候才比對，因為那時它是一份會被匯入 GitHub 的東西，少列一個 job 等於那個 job
# 不再擋 merge，而且沒有任何症狀。注意這支腳本只能確認 JSON 的內容對得上 ci.yml，
# **不能**確認 JSON 真的被匯入 GitHub —— 那是 repo 設定，沒有檢查器守得到
# （見 docs/development.md 的分支保護）。
set -euo pipefail

# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

readonly WORKFLOW=".github/workflows/ci.yml"
readonly RULESET=".github/rulesets/main.json"
# 這幾個只在 push 上跑，PR 上不存在，所以永遠不能當 required check ——
# 列進去的話每個 PR 都會卡在等一個不會來的檢查。
readonly NOT_REQUIRED="publish pushed-via-pr"

failed=0

# 下游可以整套不用 GitHub Actions（見 TEMPLATE.md 第 5 步的第三個選項）。
# 那不是壞掉，是一個正當的狀態，所以這裡直接放行 —— 沒有 CI 就沒有「CI 與本機漂移」。
if [ ! -f "$WORKFLOW" ]; then
    echo "沒有 ${WORKFLOW}，跳過（這個專案不用 GitHub Actions）"
    exit 0
fi


# --- 1. 四支腳本裡的指令都要出現在 ci.yml ---

# 腳本裡實際執行的那幾行長這樣：`(cd apps/api && uv run mypy)`。取出括號裡 `&&` 之後那段。
commands="$(sed -nE 's/^\(cd apps\/[a-z]+ && (.+)\)$/\1/p' \
    scripts/lint.sh scripts/typecheck.sh scripts/test.sh scripts/build.sh)"

# 一條都沒抽到代表這支腳本自己壞了（腳本改了寫法、或路徑錯）。
# 這時候「全部通過」是最危險的結果，所以當成失敗。
[ -n "$commands" ] || { echo "抽不到任何指令，檢查器本身壞了" >&2; exit 1; }

while IFS= read -r command; do
    grep -Fq -- "$command" "$WORKFLOW" \
        || { echo "$WORKFLOW 沒有跑到這條指令：$command" >&2; failed=1; }
done <<< "$commands"

# --- 2. ruleset 的 required checks == ci.yml 裡 PR 上會跑的 job ---

# `jobs:` 之後、縮排兩格的 `name:`。`on:` 與 `concurrency:` 底下的鍵縮排一樣，
# 所以非得先等到 `jobs:` 不可。
# 排除清單用 -v 傳進 awk，不要內插進程式字串：那樣多一個名字就要多改一次跳脫。
jobs="$(awk -v skip="$NOT_REQUIRED" '
    BEGIN { n = split(skip, list, " "); for (i = 1; i <= n; i += 1) excluded[list[i]] = 1 }
    /^jobs:[[:space:]]*$/ { in_jobs = 1; next }
    /^[^[:space:]]/       { in_jobs = 0 }
    in_jobs && /^  [a-z][a-z0-9_-]*:[[:space:]]*$/ {
        name = $1
        sub(/:$/, "", name)
        if (!(name in excluded)) print name
    }
' "$WORKFLOW" | sort)"

[ -n "$jobs" ] || { echo "在 $WORKFLOW 找不到任何 job，檢查器本身壞了" >&2; exit 1; }

if [ ! -f "$RULESET" ]; then
    echo "沒有 ${RULESET}，跳過分支保護那一半（它是選配的，見 docs/development.md）"
else
    # ruleset 是我們自己寫的 JSON，用 grep 取 context 就夠 —— 為了這一件事要求裝 jq 不划算。
    contexts="$(grep -oE '"context"[[:space:]]*:[[:space:]]*"[^"]+"' "$RULESET" \
        | sed -E 's/.*"([^"]+)"$/\1/' | sort)"

    if [ "$jobs" != "$contexts" ]; then
        echo "$RULESET 要求的 status check 與 $WORKFLOW 的 job 對不上：" >&2
        comm -23 <(echo "$jobs") <(echo "$contexts") | sed 's/^/  ci.yml 有、ruleset 沒要求：/' >&2
        comm -13 <(echo "$jobs") <(echo "$contexts") | sed 's/^/  ruleset 要求、ci.yml 沒有：/' >&2
        echo "  （$NOT_REQUIRED 只在 push 上跑，PR 上不存在，刻意不列入）" >&2
        failed=1
    fi
fi

if [ "$failed" -ne 0 ]; then
    echo >&2
    echo "CI 與本機指令／分支保護對不上。動過 ruleset 的話要重新匯入 GitHub 才會生效：" >&2
    echo "  gh api --method POST repos/{owner}/{repo}/rulesets --input $RULESET" >&2
    exit 1
fi

echo "ci.yml 跑到了 check 的每一條指令，ruleset（若有）也涵蓋所有 PR 上的 job"
