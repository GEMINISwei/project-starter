#!/usr/bin/env bash
#
# 這個 PR 改動或刪掉了**既有**的測試時，要求 PR 描述說明為什麼。
#
# 擋的是跟 AI agent 一起開發時最常見、也最安靜的失敗模式：改了實作、測試變紅，
# 於是把測試改成會過的樣子。三層規格在這裡全部失效 —— 實作級的規格就是測試本身，
# 而它被改成了實作現在的行為，紅燈消失、規格也跟著消失。
#
# **只看「刪掉的行」，不看「新增的行」。** 新增測試與程式一起進來是正常的開發，
# 每個 PR 都攔一次的話這支會被當成雜訊而繞過。而修改或刪除既有測試的斷言，
# 一定會在 numstat 的 deleted 欄留下痕跡 —— 那才是要有人講一句話的動作。
#
# **沒有 [skip ...] 逃生門，那是刻意的。** 說明本身就是逃生門：合理的情況
# （斷言本來就寫錯、介面改名、相依升級換掉 mock）寫一句就過得了，
# 而寫不出那一句的時候，正是這支要攔下來的時候。
set -euo pipefail

# shellcheck source=scripts/lib/pr.sh
source "$(dirname "$0")/lib/pr.sh"

readonly HEADING="## 改動到既有測試"
readonly TEST_DIRS=("apps/api/tests" "apps/web/tests")

# CI 用 base ref 而不是寫死 main，日後開 release 分支時這支不必跟著改（同 changelog job）。
base="${BASE_REF:-main}"
if git rev-parse --verify --quiet "origin/${base}" > /dev/null; then
    base="origin/${base}"
elif ! git rev-parse --verify --quiet "$base" > /dev/null; then
    echo "找不到基準分支 ${base}，跳過"
    exit 0
fi

if ! merge_base="$(git merge-base "$base" HEAD 2> /dev/null)"; then
    echo "與 ${base} 找不到共同祖先，跳過（CI 上請確認 checkout 的 fetch-depth 是 0）"
    exit 0
fi

# numstat 是 `新增<TAB>刪除<TAB>路徑`。刪除為 0 的是純新增，不在守備範圍。
edited="$(git diff --numstat "$merge_base" HEAD -- "${TEST_DIRS[@]}" \
    | awk -F'\t' '$2 != "0" && $2 != "-" { print "  " $3 "（-" $2 " 行）" }')"

if [ -z "$edited" ]; then
    echo "沒有改動到既有測試"
    exit 0
fi

if ! pr_context; then
    echo "讀不到 PR 描述（沒有 gh，或目前分支還沒有 PR），跳過"
    exit 0
fi

# 說明要有實際內容。HTML 註解整段跳過 —— 模板的說明就寫在那裡面，
# 不剝掉的話「原封不動的模板」會被當成已經寫了說明。
explanation="$(awk -v heading="$HEADING" '
    $0 == heading { inside = 1; next }
    inside && /^## / { inside = 0 }
    !inside { next }
    /<!--/ { comment = 1 }
    comment { if (/-->/) comment = 0; next }
    NF { print }
' <<< "$PR_BODY")"

if [ -n "$explanation" ]; then
    echo "改動到既有測試，PR 描述有說明"
    exit 0
fi

echo "這個 PR 改動或刪掉了既有的測試，但 PR 描述沒有說明：" >&2
echo "$edited" >&2
echo >&2
echo "  請在 PR 描述加一段「${HEADING}」，寫明**原本那個斷言為什麼是錯的**。" >&2
echo "  改實作讓測試變紅、再把測試改成會過的樣子，是這支要擋的東西 ——" >&2
echo "  實作級的規格就是測試，改掉它等於把規格改成「現在的行為」。" >&2
exit 1
