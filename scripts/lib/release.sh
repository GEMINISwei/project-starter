#!/usr/bin/env bash
#
# `make release` 改檔之前的檢查: 每一項失敗就印出原因並回傳非 0, 由 release.sh 依序呼叫。
# 拆成函式是為了能單獨測 (apps/api/tests/test_release_preflight.py)。
#
# 每一項都以目前目錄為準 (CHANGELOG.md、git): release.sh 經 common.sh 已經在 repo 根。
#
# 被 source 的檔案, 理由同 common.sh 不寫 `set -euo pipefail`。

[ -n "${RELEASE_SH_LOADED:-}" ] && return 0
RELEASE_SH_LOADED=1

# shellcheck source=scripts/lib/common.sh
source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

# SemVer 的 X.Y.Z, 每段不可有前導零: deploy.yml 要求 tag 是 `v<版號>`, 混進空白或斜線的版號
# 建不出合法的 tag; 前導零則會讓 version_gt 的算術把它當成八進位。
require_version_format() {
    if ! [[ "$1" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
        echo "版號要是 X.Y.Z（每段是數字，不可有前導零），例如 make release 0.0.3" >&2
        return 1
    fi
}

# 前者大於後者時回傳 0。逐段比數字, 不是比字串: 字串比較下 0.10.0 會小於 0.9.0。
version_gt() {
    local a1 a2 a3 b1 b2 b3
    IFS=. read -r a1 a2 a3 <<< "$1"
    IFS=. read -r b1 b2 b3 <<< "$2"
    if (( 10#$a1 != 10#$b1 )); then (( 10#$a1 > 10#$b1 )); return; fi
    if (( 10#$a2 != 10#$b2 )); then (( 10#$a2 > 10#$b2 )); return; fi
    (( 10#$a3 > 10#$b3 ))
}

# 只看「比目前大」不夠: APP_VERSION、CHANGELOG 與 tag 三者曾經不同步時 (例如建過 tag 卻沒合併
# 版號的修改), 比目前大的版號仍可能已經用過。tag 那一項要等 fetch 之後才準, 另見 require_untagged_version。
require_new_version() {
    local version="$1" current="$2"
    if ! version_gt "${version}" "${current}"; then
        echo "新版號 ${version} 必須大於目前的 ${current}" >&2
        return 1
    fi
    if grep -qxF "## [${version}]" CHANGELOG.md; then
        echo "CHANGELOG.md 已經有 [${version}] 的段落" >&2
        return 1
    fi
}

# [Unreleased] 底下沒有任何條目就發版, CHANGELOG 會多一個空的版本段落 —— 多半是忘了寫。
require_unreleased_entries() {
    local unreleased
    unreleased="$(awk '/^## \[Unreleased\]/ { found = 1; next } found && /^## \[/ { exit } found && NF { print }' CHANGELOG.md)"
    if [ -z "${unreleased}" ]; then
        echo "CHANGELOG.md 的 [Unreleased] 是空的，先寫下這一版改了什麼" >&2
        return 1
    fi
}

# 沒 commit 的改動會跟版號修改混在同一個 commit 裡, 而那些改動沒經過 CI。
require_clean_tree() {
    if [ -n "$(git status --porcelain)" ]; then
        echo "工作目錄有沒 commit 的改動，先 commit 或還原再發版：" >&2
        git status --short >&2
        return 1
    fi
}

# 發版的基礎必須就是 CI 驗過的 origin/main: 落後代表漏了別人合併的東西, 超前代表有沒走 PR 的
# commit。fetch 帶 --tags, 之後的 require_untagged_version 才看得到遠端剛建的 tag。
require_synced_main() {
    local branch
    branch="$(git symbolic-ref --quiet --short HEAD || true)"
    if [ "${branch}" != "main" ]; then
        echo "要在 main 上發版（目前在 ${branch:-detached HEAD}）" >&2
        return 1
    fi
    if ! git fetch --quiet --tags origin; then
        echo "無法 fetch origin，確認網路與遠端設定" >&2
        return 1
    fi
    if [ "$(git rev-parse HEAD)" != "$(git rev-parse origin/main)" ]; then
        echo "本機 main 與 origin/main 不一致：先 git pull；本機多出的 commit 要走 PR" >&2
        return 1
    fi
}

require_untagged_version() {
    if git rev-parse --quiet --verify "refs/tags/v$1" > /dev/null; then
        echo "tag v$1 已經存在" >&2
        return 1
    fi
}

# 版號的修改也要走 PR (main 只透過 PR 前進): release.sh 改完檔就切到這個分支。
release_branch() {
    printf 'chore/release-v%s\n' "$1"
}

# 上一次發版失敗留下的分支: 切過去會混進舊的修改。origin 的那一份要等 require_synced_main 的 fetch 才看得到。
require_no_release_branch() {
    local branch
    branch="$(release_branch "$1")"
    if git rev-parse --quiet --verify "refs/heads/${branch}" > /dev/null \
        || git rev-parse --quiet --verify "refs/remotes/origin/${branch}" > /dev/null; then
        echo "分支 ${branch} 已經存在：上次發版沒有收尾，先合併或刪掉它" >&2
        return 1
    fi
}

# release 的內文: changelog_section <版號> [檔案], CHANGELOG 中這個版號的段落, 去掉前後的空行。
# 可以指定檔案: 發布時讀的是 origin/main 上的那一份。
changelog_section() {
    local section
    section="$(awk -v heading="## [$1]" '
        $0 == heading { found = 1; next }
        found && /^## \[/ { exit }
        found { lines[++n] = $0 }
        END {
            first = 1; while (first <= n && lines[first] !~ /[^[:space:]]/) first++
            last = n; while (last >= first && lines[last] !~ /[^[:space:]]/) last--
            for (i = first; i <= last; i++) print lines[i]
        }' "${2:-CHANGELOG.md}")"
    if [ -z "${section}" ]; then
        echo "CHANGELOG.md 沒有 [$1] 的段落，或段落是空的" >&2
        return 1
    fi
    printf '%s\n' "${section}"
}

# 指定 commit 上的 APP_VERSION: 要發布的是合併後的 origin/main, 不是工作目錄裡的檔案。
version_at_ref() {
    local version
    version="$(git show "$1:apps/api/app/config.py" 2> /dev/null | sed -n 's/^APP_VERSION = "\(.*\)"$/\1/p')"
    if [ -z "${version}" ]; then
        echo "$1 上的 apps/api/app/config.py 找不到 APP_VERSION" >&2
        return 1
    fi
    printf '%s\n' "${version}"
}

# 發布要做什麼: release_action <none|prerelease|release> <prerelease|release>, 印出 create 或 promote。
# 先行測試沒問題時改成正式版用同一個 tag (deploy.yml 聽 released), 不另建。
release_action() {
    local state="$1" mode="$2"
    case "${state}" in
        none) echo create ;;
        prerelease)
            if [ "${mode}" = prerelease ]; then
                echo "這一版已經是 pre-release；要改成正式版就不要帶 --prerelease" >&2
                return 1
            fi
            echo promote
            ;;
        *)
            echo "這一版已經發布成正式版；重新部署請在 Actions 的 Deploy 按 Run workflow" >&2
            return 1
            ;;
    esac
}
