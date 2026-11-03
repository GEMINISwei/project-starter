#!/usr/bin/env bash
#
# preview.sh 與 publish.sh 共用: 從合併後的 origin/main 算出這次發布要做什麼, 並印出來。
#
# 被 source 的檔案, 理由同 scripts/lib/common.sh 不寫 `set -euo pipefail`。

# shellcheck source=scripts/lib/release.sh
source "$(git rev-parse --show-toplevel)/scripts/lib/release.sh"

# plan_release <版號> <prerelease|release>: 設定 TAG、TARGET、ACTION、NOTES_FILE 並印出摘要。
# 任何一項不對就回傳非 0, 什麼都不做。
plan_release() {
    local version="$1" mode="$2" on_main state targets_var
    require_version_format "${version}" || return 1
    git fetch --quiet --tags origin || { echo "無法 fetch origin" >&2; return 1; }

    # tag 必須打在版號已經合併進去的 commit 上: deploy.yml 會檢查 tag 等於 v<APP_VERSION>。
    TARGET="$(git rev-parse origin/main)"
    on_main="$(version_at_ref origin/main)" || return 1
    if [ "${on_main}" != "${version}" ]; then
        echo "origin/main 的 APP_VERSION 是 ${on_main}，不是 ${version}：發版的 PR 還沒合併？" >&2
        return 1
    fi

    TAG="v${version}"
    state="$(gh release list --limit 1000 --json tagName,isPrerelease \
        --jq ".[] | select(.tagName == \"${TAG}\") | if .isPrerelease then \"prerelease\" else \"release\" end")"
    ACTION="$(release_action "${state:-none}" "${mode}")" || return 1
    if [ "${ACTION}" = create ]; then
        require_untagged_version "${version}" || return 1
    fi

    NOTES_FILE="$(mktemp)"
    changelog_section "${version}" <(git show origin/main:CHANGELOG.md) > "${NOTES_FILE}" || return 1

    # 部署哪些組由 repo 的 Variables 決定 (deploy.yml): pre-release 給 PRE_RELEASE_TARGETS, 其餘給 PUBLISH_TARGETS。
    targets_var=PUBLISH_TARGETS
    [ "${mode}" = prerelease ] && targets_var=PRE_RELEASE_TARGETS

    if [ "${ACTION}" = promote ]; then
        echo "動作：把 pre-release ${TAG} 改成正式版"
    elif [ "${mode}" = prerelease ]; then
        echo "動作：建立 pre-release ${TAG}"
    else
        echo "動作：建立正式版 ${TAG}"
    fi
    echo "commit：$(git log -1 --format='%h %s' "${TAG}" 2> /dev/null || git log -1 --format='%h %s' "${TARGET}")"
    echo "部署的組（${targets_var}）：$(gh variable get "${targets_var}" 2> /dev/null || echo '未設定，不會部署任何一組')"
    echo "內文："
    sed 's/^/  /' "${NOTES_FILE}"
}
