#!/usr/bin/env bash
#
# 檢查 workflow 本身，以及它與本機 check 腳本、分支保護之間有沒有漂移。
#
# 守三件事：
#
#   1. `.github/workflows/ci.yml` 真的跑到 lint／typecheck／test／build 四支腳本裡的每一條指令。
#   2. `.github/rulesets/main.json`（**選配**）要求的 status check，恰好是 ci.yml 裡
#      所有會在 PR 上跑的 job。檔案不在就跳過這一半 —— 見底下。
#   3. workflow 檔本身過得了 actionlint（表達式、`if:` 條件、action 的輸入、
#      以及 `run:` 區塊裡的 shell）。
#
# 第 3 件事跟前兩件是不同層的問題，放在同一支是因為守的是同一份檔案。前兩件抓的是
# 「三處手抄的東西對不上」，actionlint 抓的是「這份 YAML 自己就寫錯了」——
# 而 workflow 的錯誤幾乎都要推上去才會現形，本機沒有任何東西在跑它。
#
# 為什麼 CI 不乾脆直接呼叫 `make lint` 那幾個 target（那樣就沒有第 1 件事要守了）：
# 那幾支腳本一支同時跑前後端兩邊，而 CI 刻意把 api 與 web 切成兩個平行 job ——
# 直接呼叫會把兩邊串成一條，PR 的等待時間大約翻倍。所以 CI 內嵌等價指令是**刻意**的，
# 代價就是「同一條指令寫在兩個地方」，由這支腳本補起來。
# （附帶一提，`load_env` 在沒有 `.env` 時是 no-op，所以「CI 不能呼叫 make」並不成立，
# 平行切分才是真正的理由。）
#
# 第 2 件事守的是**分支保護**。模板預設 repo 是 public，那時 ruleset 免費而且該匯入
# （ci.yml 讓 merge 那一輪不重跑測試，前提就是它的 strict 政策）。但這支仍然接受檔案不存在：
# private repo 在免費方案上設不了 ruleset（API 回 403），那種專案靠 .githooks/pre-push
# 與 ci.yml 的 pushed-via-pr job 那兩層。`.github/rulesets/main.json` 不在就跳過，不算失敗。
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

# --- 3. workflow 檔本身過得了 actionlint ---

# **版本釘死**：actionlint 每次升級都可能多報幾條，而那會讓一個沒動過 workflow 的 PR
# 突然變紅。升級是刻意的動作，不是自動發生的 —— 沒有任何檢查器在比對這個版本，
# 跟 apps/web/Dockerfile 的 ARG NODE_VERSION 同一類（見 docs/development.md）。
readonly ACTIONLINT_IMAGE="rhysd/actionlint:1.7.12"

# 走 docker 而不是要求主機裝 actionlint：這個 repo 本來就把 Docker Desktop 列為前置需求，
# 而 ubuntu runner **沒有**內建 actionlint（shellcheck 有，所以 check-shell 可以直接用）。
# 用 image 的話本機與 CI 跑的是同一個版本，不會出現「本機綠、CI 紅」。
#
# 沒有 docker 就跳過，比照 check-nginx 的語法檢查那一半：前兩件事是純靜態的，
# 已經跑完了，不該因為 docker 沒開就把整支判成失敗。**訊息要明講跳過了什麼** ——
# 靜靜跳過的檢查器等於沒有檢查器。
if ! command -v docker >/dev/null 2>&1 || ! docker info >/dev/null 2>&1; then
    echo "ci.yml 跑到了 check 的每一條指令，ruleset（若有）也涵蓋所有 PR 上的 job"
    echo "actionlint 略過（沒有可用的 docker）—— CI 的 deploy-config job 會跑到"
    exit 0
fi

# -no-color：這支的輸出會進 CI 的 log，ANSI 跳脫碼在那裡只是雜訊。
# -oneline：一條一行，grep 得動，也不會讓錯誤訊息在 CI 的 log 裡散成三行。
docker run --rm -v "$REPO_ROOT:/repo" --workdir /repo "$ACTIONLINT_IMAGE" -no-color -oneline || {
    echo >&2
    echo "actionlint 有發現（上面每一條都帶檔名與行號）。" >&2
    echo "  誤報請在該 run: 區塊加一行 # shellcheck disable=SCxxxx 並寫明理由，" >&2
    echo "  不要加 .github/actionlint.yaml 全域抑制 —— 那會連同類的真問題一起關掉。" >&2
    exit 1
}

echo "ci.yml 跑到了 check 的每一條指令，ruleset（若有）也涵蓋所有 PR 上的 job"
echo "workflow 檔通過 actionlint（${ACTIONLINT_IMAGE}）"
