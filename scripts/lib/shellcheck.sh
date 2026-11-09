#!/usr/bin/env bash
#
# 固定 ShellCheck 的版本: make check lint 用的版本固定, 判斷才不會隨環境變。
# (這一行不能以「shellcheck」開頭: 那會被當成它的 directive。)
#
# 不同版本對同一份腳本的判斷不同 (例如 `A && B || C` 的 SC2015): runner 內建的版本一換,
# 沒改程式的 CI 也會突然變紅。
# 版本只寫在這裡: CI 從這一行讀版本, 下載並核對 sha256 (.github/workflows/ci.yml 的 lint job);
# 升級時改這裡, 再到 ci.yml 換掉 sha256 (GitHub release 頁面的 digest)。
# 這是 Dependabot 看不到的相依, 在發版前的整批升級時一起檢查 (docs/workflow.md〈相依升級〉)。

SHELLCHECK_VERSION="0.11.0"

# 版本不同就失敗。CI 上代表安裝步驟沒有生效, 跑的仍是 runner 內建的那一版;
# 本機代表判斷可能跟 CI 不一樣, 結果不能當真。
check_shellcheck_version() {
    local version
    version="$(shellcheck --version | sed -n 's/^version: //p')"
    [ "${version}" = "${SHELLCHECK_VERSION}" ] && return 0
    echo "shellcheck 是 ${version}，應該是 ${SHELLCHECK_VERSION}（CI 上代表安裝步驟沒有生效）" >&2
    return 1
}
