#!/usr/bin/env bash
#
# 從模板拉更新：先挑出真的要動手的條目，確認後才合併。
#
# 為什麼不是直接教人下 `git merge template/main`：合併本身不難，難的是**合併之前**要
# 知道這次帶進來什麼。模板的條目絕大多數是「拉下來就好」，混在一起讀完才找得到那一兩筆
# 要動手的 —— 那個成本每次同步都要付一次，而且付不起的人就乾脆不同步了。
#
# 這支不解衝突，也不替你決定要不要合併。它只做四件事：把落後的條目按同步影響分堆、
# 顯示改動範圍、在紀律已經被破壞時先講、然後把合併交給 git。
# 衝突的處理原則在 docs/downstream.md，那裡是 owner。
set -euo pipefail

# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

readonly REMOTE="template"
readonly BRANCH="template/main"
readonly CHANGELOG="CHANGELOG.template.md"

# 模板自己跑到這裡是正常的（它沒有上游），所以不是錯誤 —— 用 exit 0 收場，
# 否則 `make sync` 在模板 repo 裡看起來像壞掉。
if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
    echo "這個 repo 沒有叫 ${REMOTE} 的 remote，沒有可以同步的上游。"
    echo "  這裡就是模板本身的話，這是預期的。"
    echo "  是下游專案的話用 make remote 綁定（名稱填 ${REMOTE}），見 docs/downstream.md。"
    exit 0
fi

# 合併會把未提交的改動一起捲進衝突，而那時要分辨「哪些是我剛寫的、哪些是上游帶來的」
# 幾乎不可能。先擋在這裡，比事後 git checkout 救便宜得多。
if [ -n "$(git status --porcelain)" ]; then
    echo "工作區有未提交的改動，先 commit 或 stash 再同步。" >&2
    exit 1
fi

echo "取得 ${REMOTE} 的最新狀態…"
git fetch -q "$REMOTE"

if ! git rev-parse --verify --quiet "$BRANCH" >/dev/null; then
    echo "${REMOTE} 沒有 main 分支 —— 用 git branch -r 看它實際有哪些分支。" >&2
    exit 1
fi

# 沒有共同祖先時 merge 會以 refusing to merge unrelated histories 收場，
# 而那個訊息看不出真正的原因（開案時沒有保留 clone 下來的歷史）。
if ! git merge-base HEAD "$BRANCH" >/dev/null 2>&1; then
    echo "${BRANCH} 與本機歷史沒有共同祖先，這個 repo 沒辦法用合併的方式同步。" >&2
    echo "理由與唯一的補救方式見 docs/downstream.md 的〈拉模板的更新〉。" >&2
    exit 1
fi

if git merge-base --is-ancestor "$BRANCH" HEAD; then
    echo "已經是最新的，${BRANCH} 的內容都在了。"
    exit 0
fi

# ── 落後的條目 ────────────────────────────────────────────────────────────────
#
# 只取 diff 的新增行：那份檔案在下游不會被改，所以新增行就是「上游有、我還沒有」的條目。
# 這正是模板與下游的變更紀錄要分成兩份檔案的理由 —— 合在一起的話這裡會同時撈到
# 下游自己寫的東西，而且分不出來。
added="$(git diff "HEAD..$BRANCH" -- "$CHANGELOG" | sed -n 's/^+\([^+]\)/\1/p;s/^+$//p')"

# 條目是多行的（續行縮排），所以要把續行接回它的第一行才能按標記分堆。
# 版號標題結束目前這一筆；沒有標記的行落在 header，忽略。
entries_matching() {
    printf '%s\n' "$added" | awk -v want="$1" '
        /^## / { keep = 0; next }
        /^- / {
            keep = 0
            # index() 比對字面值，理由同 scripts/check-version.sh 的那一段。
            if (want == "action") {
                if (index($0, "[同步:要動手]") || index($0, "[同步:破壞性]")) keep = 1
            } else {
                if (index($0, "[同步:")) keep = 1
                if (index($0, "[同步:要動手]") || index($0, "[同步:破壞性]")) keep = 0
            }
        }
        keep { print }
    '
}

action="$(entries_matching action)"
rest="$(entries_matching rest)"

echo
if [ -n "$action" ]; then
    echo "── 這幾筆同步後要動手 ───────────────────────────────────────────"
    printf '%s\n' "$action"
else
    echo "── 沒有需要動手的條目 ───────────────────────────────────────────"
fi

if [ -n "$rest" ]; then
    echo
    echo "── 其餘（拉下來就好）────────────────────────────────────────────"
    printf '%s\n' "$rest"
fi

# 條目一筆都撈不到，多半是上游這次沒動 CHANGELOG，也可能是這個下游還停在分家之前的
# 版本（那時候還沒有這份檔案）。兩種都不該當成「沒事」，直接說出來讓人自己看 diff。
if [ -z "$action" ] && [ -z "$rest" ]; then
    echo "（${CHANGELOG} 沒有新增條目。上游這次可能只動了不需要條目的東西，"
    echo "  也可能是這個 repo 還沒同步過「變更紀錄分家」那一版 —— 底下的檔案清單為準。）"
fi

echo
echo "── 會影響到的範圍 ───────────────────────────────────────────────"
# 只看這三個目錄：CI 的 changelog job 用的也是它們，所以「有條目卻沒有檔案改動」
# 或反過來，都是值得看一眼的訊號。
stat="$(git diff --stat "HEAD..$BRANCH" -- apps/ scripts/ infra/)"
if [ -n "$stat" ]; then
    printf '%s\n' "$stat"
else
    echo "（apps/、scripts/、infra/ 都沒有改動，這次只動了文件或 CI 設定）"
fi

# 下游改過 shared/ 的話，這次合併幾乎一定要手解，而原因不在這次的改動裡 ——
# 先講，比在衝突訊息裡才發現便宜。比的是 merge-base 到 HEAD，也就是「我自己動過什麼」。
base="$(git merge-base HEAD "$BRANCH")"
touched_shared="$(git diff --name-only "$base" HEAD -- 'apps/*/shared/')"
if [ -n "$touched_shared" ]; then
    echo
    echo "注意：這個 repo 自己改過 shared/，同步紀律已經被破壞（見 docs/downstream.md）："
    printf '%s\n' "$touched_shared" | sed 's/^/  /'
    echo "  這幾個檔案很可能要手解，而正確的作法是把它們送回上游而不是在這裡硬解。"
fi

echo
confirm "要合併 ${BRANCH} 嗎？"

if git merge "$BRANCH"; then
    echo
    echo "✓ 合併完成。接著跑："
    echo "    make gen-types   # 後端 schema 有變動時，前端型別要跟著重產"
    echo "    make check"
    exit 0
fi

# git 的衝突清單已經印在上面了，這裡只補「怎麼解」的分類 —— 三類的解法不同，
# 混著解會解錯。完整說明在 docs/downstream.md。
echo
echo "有衝突要解。三類的解法不一樣，不要混著解（詳見 docs/downstream.md）：" >&2
echo "  清單（ENABLED_MODULES、Permission、nav-icons）→ 兩邊的項目都保留" >&2
echo "  token 與主題（app/tokens、app/themes）→ 值留自己的，解完跑 npm run check:tokens" >&2
echo "  APP_VERSION（apps/api/app/config.py）→ 留自己的，那是你的產品版號" >&2
echo "  shared/ 底下 → 紀律被破壞了，先把你的修改送回上游，不要在這裡硬解" >&2
exit 1
