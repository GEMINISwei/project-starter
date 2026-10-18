#!/usr/bin/env bash
#
# 發版前的版號更新: make release <版號> (例如 make release 0.0.3)
#
#   make release 0.0.3   把 APP_VERSION 改成 0.0.3, CHANGELOG 的 [Unreleased] 改成這個版號
#
# 跟 git tag 對齊的版號只有這兩處 (前端的版號經 API 取自 APP_VERSION), 由這支腳本一起改,
# `make check` 的 `apps/api/tests/test_version.py` 擋住兩者不一致。
# pyproject.toml、package.json 與 lock 檔刻意不跟發版: 那些是套件自己的版號, 有實際變更時才改,
# git 上的 diff 才有意義。OpenAPI 的 info.version 固定不動 (見 shared/platform.py)。
#
# 改檔之前先檢查 (scripts/lib/release.sh), 任何一項不過就停, 什麼都不改: 這是本機的指令,
# 等 push 之後才由 CI 發現就太晚了。契約只比對不重產 —— 不一致代表 main 上有繞過 CI 的東西,
# 要先走 PR 修好, 不該默默包進發版的 commit。
#
# 只改檔案, 不 commit 也不建 tag: 跑完看過 diff 再 commit, 然後照 docs/operations.md〈發版〉建 release。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib/release.sh
source "$SCRIPT_DIR/lib/release.sh"
# shellcheck source=scripts/lib/contract.sh
source "$SCRIPT_DIR/lib/contract.sh"

version="${1:-}"
require_version_format "${version}"
current="$(app_version)"
# 不需要網路的先做, 錯了馬上知道; fetch 之後 tag 的檢查才準; 契約最慢, 放最後。
require_new_version "${version}" "${current}"
require_unreleased_entries
require_clean_tree
require_synced_main
require_untagged_version "${version}"
load_env
check_contract

# 每一處都用「只會命中那一行」的樣式改, 不做全檔取代。
#
# 先全部改在暫存的複本上, 每一處都改成功才一起寫回: 改到一半失敗的話, 留下「一半是新版號」的
# repo 比整個失敗更難收拾。
stage="$(mktemp -d)"
trap 'rm -rf "${stage}"' EXIT

replace() {
    local file="$1" pattern="$2" replacement="$3"
    local staged="${stage}/${file}"
    if [ ! -f "${staged}" ]; then
        mkdir -p "$(dirname "${staged}")"
        cp "${file}" "${staged}"
    fi
    local before
    before="$(cat "${staged}")"
    # -0: 整個檔案當一個字串, 樣式才能跨行; (?m): 讓 ^ 對每一行的開頭生效。
    perl -0pi -e "s/(?m)${pattern}/${replacement}/" "${staged}"
    if [ "$(cat "${staged}")" = "${before}" ]; then
        echo "${file} 裡找不到要改的版號（樣式：${pattern}）, 沒有改動任何檔案" >&2
        exit 1
    fi
}

replace apps/api/app/config.py '^APP_VERSION = "[^"]*"' "APP_VERSION = \"${version}\""
# 新版本段落插在 [Unreleased] 正下方, [Unreleased] 留著給下一版用。
replace CHANGELOG.md '^## \[Unreleased\]\n' "## [Unreleased]\n\n## [${version}]\n"

(cd "${stage}" && find . -type f) | while read -r file; do
    cp "${stage}/${file}" "${file}"
done
echo
echo "版號已從 ${current} 改成 ${version}。看過 git diff 之後 commit，再建 tag v${version} 的 release。"
