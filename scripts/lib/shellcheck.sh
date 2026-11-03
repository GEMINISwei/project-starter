#!/usr/bin/env bash
#
# 固定 ShellCheck 的版本: 本機的 make check 與 CI 用同一版, 判斷才一致。
# (這一行不能以「shellcheck」開頭: 那會被當成它的 directive。)
#
# 不同版本對同一份腳本的判斷不同 (例如 `A && B || C` 的 SC2015), 版本不一致時會本機綠、CI 紅。
# 版本只寫在這裡: CI 從這一行讀版本, 下載並核對 sha256 (.github/workflows/ci.yml 的 check job);
# 升級時改這裡, 再到 ci.yml 換掉 sha256 (GitHub release 頁面的 digest)。
# 這是 Dependabot 看不到的相依, 在發版前的整批升級時一起檢查 (docs/workflow.md〈相依升級〉)。

SHELLCHECK_VERSION="0.11.0"

# 本機版本不同只提醒: 升級由各自的套件管理決定, 不該因此不能檢查。
# CI 上不同就失敗: 那代表安裝步驟沒有生效, 跑的仍是 runner 內建的那一版。
check_shellcheck_version() {
    local version
    version="$(shellcheck --version | sed -n 's/^version: //p')"
    [ "${version}" = "${SHELLCHECK_VERSION}" ] && return 0
    if [ -n "${CI:-}" ]; then
        echo "CI 的 shellcheck 是 ${version}，應該是 ${SHELLCHECK_VERSION}（安裝步驟沒有生效）" >&2
        return 1
    fi
    echo "⚠️  本機的 shellcheck 是 ${version}，CI 用的是 ${SHELLCHECK_VERSION}；判斷可能不同，本機綠不代表 CI 綠。" >&2
}
