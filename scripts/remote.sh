#!/usr/bin/env bash
#
# 互動式綁定 git remote（名稱預設 origin）。
#
# 為什麼獨立成一支、不併進 make init：本機開發測試時常常不想綁任何儲存庫，而 init 是
# 「跑完就能 make dev」的那一步，不該為了一個可以不填的網址就需要網路。
#
# 這支做的事比 `git remote add` 多三件，而那三件正是它存在的理由：
#   1. 綁定前先用 ls-remote 確認真的連得上（打錯字不會留下一個壞掉的 remote）。
#   2. 綁定後說明這個 remote 接下來能怎麼用 —— 連得上不等於接得起來，見底下 report_usage。
#   3. 推得上去的時候直接問要不要推，不用再自己下一次 git push。
set -euo pipefail

# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

if [ ! -e .git ]; then
    echo "這裡還不是 git repo（請先執行 make init，或自己 git init）" >&2
    exit 1
fi

# y/N 詢問，答 N 回傳非 0。
#
# 不用 common.sh 的 confirm()：那一支是給破壞性操作用的，答 N 會以 exit 1 收場。
# 這支腳本裡「不改網址」與「不推上去」都是正常結果，不該讓 make remote 看起來失敗。
ask_yes() {
    local ans
    printf '%s [y/N] ' "$1"
    read -r ans
    [ "$ans" = "y" ] || [ "$ans" = "Y" ]
}

# ── 推上去 ────────────────────────────────────────────────────────────────────
#
# 只有 report_usage 判定「推得上去」的兩種狀態會呼叫這裡（遠端是空的、本機領先可快轉）。
# 推不上去的狀態不問 —— 問一個註定失敗的問題，只會把 git 的 non-fast-forward 錯誤
# 變成使用者以為是自己答錯了。
offer_push() {
    local name="$1" branch
    branch="$(git branch --show-current)"

    # template 是「拉更新的上游」，不是要推上去的地方。而且下游是 clone 來的、歷史相通，
    # push 會真的快轉成功 —— 把專案自己的 commit 寫進模板，而且不會有任何錯誤訊息。
    # 這個名稱在 docs/downstream.md 與 AGENTS.md 都是有定義的約定，所以直接依名稱擋。
    if [ "$name" = "template" ]; then
        echo "template 是拉更新用的上游，不從這裡推上去。"
        return
    fi

    # detached HEAD 時 --show-current 是空字串，推一個空分支名會變成看不懂的錯。
    if [ -z "$branch" ]; then
        echo "目前是 detached HEAD，先切到一個分支再推。"
        return
    fi

    if ! ask_yes "要現在把 $branch 推到 $name 嗎？"; then
        echo "沒有推送。之後要推：git push -u $name $branch"
        return
    fi

    # 不吃掉 git 的輸出：推送進度與失敗原因都要讓使用者看到。
    if git push -u "$name" "$branch"; then
        echo "✓ 已推送 $branch → $name"
    else
        echo "✗ 推送失敗（原因見上方 git 的訊息）" >&2
        return 1
    fi
}

# ── 綁定之後怎麼用 ────────────────────────────────────────────────────────────
#
# 「連得上」與「接得起來」是兩件事，而第二件只有在第一次 merge 時才會現形 ——
# 那時專案已經長出來了，發現得愈晚愈貴。所以在綁定當下就把狀況講完。
report_usage() {
    local name="$1"

    # 一律問本機的 remote-tracking ref，不再打一次網路：上面的 fetch 已經把狀態帶回來了。
    # 遠端一個 ref 都沒有 = 全新的空儲存庫。這是開新專案最常見的情況。
    if [ -z "$(git for-each-ref "refs/remotes/$name")" ]; then
        echo "遠端目前是空的。"
        offer_push "$name"
        return
    fi

    if ! git rev-parse --verify --quiet "$name/main" >/dev/null; then
        echo "遠端有內容，但沒有 main 分支 —— 用 git branch -r 看它實際有哪些分支。"
        return
    fi

    # 還沒有任何 commit（git init 之後沒 commit 過）時，下面的 merge-base 一定失敗，
    # 但那不是「歷史對不上」，只是還沒有歷史可以對。
    if ! git rev-parse --verify --quiet HEAD >/dev/null; then
        echo "本機還沒有任何 commit。先 commit，再決定要 merge 還是直接以遠端為準。"
        return
    fi

    # merge-base 找不到共同祖先時退出碼非 0。這正是「rm -rf .git 之後重開歷史，
    # 再把原本的儲存庫加回來」會落到的狀態：兩邊各有各的 root commit。
    if git merge-base HEAD "$name/main" >/dev/null 2>&1; then
        # 「接得起來」不等於「推得上去」，所以這一支還要再分三種。
        # 相同必須排在最前面：--is-ancestor 對同一個 commit 也成立，不先擋掉的話
        # 會問一個推完只會得到 Everything up-to-date 的問題。
        if [ "$(git rev-parse HEAD)" = "$(git rev-parse "$name/main")" ]; then
            echo "本機與 $name/main 一致，不用做什麼。"
        elif git merge-base --is-ancestor "$name/main" HEAD; then
            echo "本機領先 $name/main。"
            offer_push "$name"
        else
            echo "本機落後或已與 $name/main 分岔，先合併再推："
            echo "    git merge $name/main"
        fi
        return
    fi

    echo "注意：$name/main 與本機歷史**沒有共同祖先**。"
    echo "    git merge $name/main 會以 refusing to merge unrelated histories 失敗；"
    echo "    加上 --allow-unrelated-histories 才跑得動，但因為沒有 merge base，"
    echo "    幾乎每個檔案都會變成衝突。要當成可持續同步的上游，請改用 git clone 開案。"
}

# ── 1. 遠端名稱 ───────────────────────────────────────────────────────────────
while :; do
    printf '遠端名稱 [origin]: '
    read -r remote_name
    remote_name="${remote_name:-origin}"
    case "$remote_name" in
        *[!A-Za-z0-9._-]*) echo "遠端名稱只能包含英文字母、數字、.、_、-" ;;
        *) break ;;
    esac
done

# 同名已存在時不要默默覆蓋：remote 指錯地方的後果是推到別人的儲存庫。
update_existing=0
if existing_url="$(git remote get-url "$remote_name" 2>/dev/null)"; then
    echo "$remote_name 已經綁定：$existing_url"
    if ! ask_yes "要改成另一個網址嗎？"; then
        echo "保持原樣，沒有變更任何設定"
        exit 0
    fi
    update_existing=1
fi

# ── 2. 網址 ───────────────────────────────────────────────────────────────────
while :; do
    printf '遠端網址（留空取消）：'
    read -r remote_url
    if [ -z "$remote_url" ]; then
        echo "已取消，沒有變更任何設定"
        exit 0
    fi

    # 唯讀探測，不留下任何本機狀態 —— 打錯字時不會留下一個連不上的 remote。
    # 刻意不設 GIT_TERMINAL_PROMPT=0：私有儲存庫走 HTTPS 時 git 本來就會問帳密，
    # 這是互動指令，讓它照常問，比「失敗但看不出是少了認證」好。
    printf '確認連線中…'
    if git ls-remote "$remote_url" >/dev/null 2>&1; then
        echo " ✓ 連得上"
        break
    fi
    echo " ✗ 連不上"
    echo "  網址、存取權限或網路其中之一有問題，請重新輸入（留空取消）"
done

# ── 3. 綁定並取得遠端狀態 ─────────────────────────────────────────────────────
if [ "$update_existing" -eq 1 ]; then
    git remote set-url "$remote_name" "$remote_url"
else
    git remote add "$remote_name" "$remote_url"
fi

git fetch -q "$remote_name"
echo "✓ 已綁定 $remote_name → $remote_url"
echo

report_usage "$remote_name"
