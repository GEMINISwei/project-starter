#!/usr/bin/env bash
#
# 發版前的版號更新: make release <版號> (例如 make release 0.0.3)
#
#   make release 0.0.3   把 APP_VERSION 改成 0.0.3, CHANGELOG 的 [Unreleased] 改成這個版號
#
# 跟 git tag 對齊的版號只有這兩處 (前端的版號經 API 取自 APP_VERSION), 由這支腳本一起改,
# `make check` 的 `apps/api/tests/test_version.py` 擋住兩者不一致。
# pyproject.toml、package.json、lock 檔與 OpenAPI 的 info.version 刻意不跟發版:
# 那些是套件與契約自己的版號, 有實際變更時才改, git 上的 diff 才有意義。
#
# 只改檔案, 不 commit 也不建 tag: 跑完看過 diff 再 commit, 然後照 docs/operations.md〈發版〉建 release。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/lib/common.sh
source "$SCRIPT_DIR/lib/common.sh"

version="${1:-}"
# 只收 X.Y.Z: deploy.yml 要求 tag 是 `v<版號>`, 混進空白或斜線的版號建不出合法的 tag。
if ! [[ "${version}" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "用法：make release <版號>，例如 make release 0.0.3" >&2
    exit 1
fi

current="$(app_version)"
if [ "${version}" = "${current}" ]; then
    echo "目前已經是 ${current}" >&2
    exit 1
fi

# [Unreleased] 底下沒有任何條目就發版, CHANGELOG 會多一個空的版本段落 —— 多半是忘了寫。
unreleased="$(awk '/^## \[Unreleased\]/ { found = 1; next } found && /^## \[/ { exit } found && NF { print }' CHANGELOG.md)"
if [ -z "${unreleased}" ]; then
    echo "CHANGELOG.md 的 [Unreleased] 是空的，先寫下這一版改了什麼" >&2
    exit 1
fi

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
