#!/usr/bin/env bash
#
# 確認 PR 描述裡的每一條驗收條件都指得出一個真的存在的測試。
#
# 這支守的是三層規格裡的**功能級**那一層（見 docs/development.md 的
# 「規格與測試的三層」）。功能級規格漂移的樣子很固定：形容詞式的條件（「回應要快」）、
# 一條塞多件事、以及 AI 生成時特別容易出現的佔位條目 —— 三種都不會讓任何測試變紅，
# 因為它們根本沒有對應的測試。
#
# 檢查的方式是**要求每條驗收條件指名一個測試**，而不是去解析自然語言：
# 你寫不出「回應要快」的測試名稱，所以那個格式本身就是文法。這也是這個 repo
# 不引入 Gherkin 卻仍然有約束的原因 —— 約束來自「必須指得出一個可執行的斷言」，
# 不是來自 Given/When/Then 那組關鍵字。
#
# **只驗正方向（驗收條件 → 測試）。** 反方向（每個測試都要追得回一條驗收條件）刻意不做：
# 這個 repo 有大量不變條件測試（`test_unlogged_paths_only_contains_liveness_probes`、
# 「路徑不重複」），它們沒有使用者可見的驗收條件，而且不該有。強制反向只會逼人替它們
# 捏造驗收條件 —— 那正好是這支要擋的東西。
#
# **測試還不存在時它是紅的**：流程是先開 draft PR 寫驗收條件、再寫測試，所以這支就是
# 功能級的紅綠燈，紅到測試進版控為止。**在本機跑它是刻意的用法** —— 它讀得到當前分支的
# PR，而 CI 上的 acceptance job 在 draft 期間跳過（理由見 ci.yml 那個 job 的註解）。
set -euo pipefail

# shellcheck source=scripts/lib/pr.sh
source "$(dirname "$0")/lib/pr.sh"

readonly HEADING="## 驗收條件"
readonly TEST_DIRS=("apps/api/tests" "apps/web/tests")

if ! pr_context; then
    echo "讀不到 PR 描述（沒有 gh，或目前分支還沒有 PR），跳過"
    exit 0
fi

# 純文件、CI 調整、相依升級那類沒有行為變更的 PR 用逃生門。
if pr_skipped "skip acceptance"; then
    echo "PR 標題帶 [skip acceptance]，略過檢查"
    exit 0
fi

section="$(awk -v heading="$HEADING" '
    $0 == heading { inside = 1; next }
    inside && /^## / { inside = 0 }
    inside { print }
' <<< "$PR_BODY")"

# 逐條抽出驗收條件與它指名的測試。
#
# HTML 註解整段跳過：PR 模板的說明與**範例**就寫在這一節的註解裡，不剝掉的話
# 範例會被當成真的驗收條件 —— 那是「檢查器看起來在跑，其實在驗自己的模板」。
parsed="$(awk '
    function flush() {
        if (item != "" && !named) print "MISSING\t" item
        item = ""
        named = 0
    }
    /<!--/ { comment = 1 }
    comment { if (/-->/) comment = 0; next }
    /^[[:space:]]*-[[:space:]]/ { flush(); item = $0 }
    {
        if ($0 !~ /(→|->)/) next
        rest = $0
        while (match(rest, /`[^`]+`/)) {
            print "NAME\t" substr(rest, RSTART + 1, RLENGTH - 2)
            rest = substr(rest, RSTART + RLENGTH)
            named = 1
        }
    }
    END { flush() }
' <<< "$section")"

failed=0

# 一條都沒抽到：驗收條件那一節空著、只剩模板的佔位符號，或整節被刪掉。
# 三者都是「這個 PR 沒有講定做完長什麼樣」，不是檢查器沒事做。
if ! grep -q '^\(MISSING\|NAME\)' <<< "$parsed"; then
    echo "PR 描述裡抽不到任何驗收條件。" >&2
    echo "  「${HEADING}」那一節要有至少一條，格式見 .github/PULL_REQUEST_TEMPLATE.md。" >&2
    echo "  純文件或 CI 調整這類沒有行為變更的改動，在 PR 標題加上 [skip acceptance]。" >&2
    exit 1
fi

while IFS=$'\t' read -r kind value; do
    [ "$kind" = "MISSING" ] || continue
    echo "這條驗收條件沒有指名測試：${value}" >&2
    failed=1
done <<< "$parsed"

if [ "$failed" -ne 0 ]; then
    echo "  每條後面要接一行「→ 測試名稱」，測試名稱用反引號包起來。" >&2
    echo "  寫不出測試名稱代表那一條還沒被想清楚 —— 那就是動手前要問掉的地方。" >&2
    exit 1
fi

# 指名的測試要真的在版控裡。這一段順帶擋掉「驗收條件指著的測試被刪掉」——
# 覆蓋率地板刻意訂得寬（見 pyproject.toml 與 vitest.config.ts），擋不到那件事。
while IFS=$'\t' read -r kind value; do
    [ "$kind" = "NAME" ] || continue
    # 前端測試名是中文句子，驗收條件裡常連著引號一起寫；剝掉再比對，兩種寫法都收。
    needle="${value%\"}"
    needle="${needle#\"}"
    if ! grep -rFq -- "$needle" "${TEST_DIRS[@]}"; then
        echo "找不到這個測試：${needle}" >&2
        failed=1
    fi
done <<< "$parsed"

if [ "$failed" -ne 0 ]; then
    echo "  測試要在 ${TEST_DIRS[*]} 底下，名稱與驗收條件裡寫的一字不差。" >&2
    echo "  還沒寫是正常的（draft PR 先寫驗收條件），寫完這支就會綠。" >&2
    exit 1
fi

count="$(grep -c '^NAME' <<< "$parsed")"
echo "驗收條件都指得出測試（${count} 條）"
