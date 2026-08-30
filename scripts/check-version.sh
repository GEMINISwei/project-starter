#!/usr/bin/env bash
#
# 確認版號三者一致：APP_VERSION、CHANGELOG 的最新版號條目、發版時的 git tag。
#
# 這支存在的理由：三者對不上是**沒有症狀**的 —— CI 的 pr-checks 只擋「有沒有寫條目」，
# 擋不到「條目的版號跟程式裡的版號對不起來」。
#
# registry 模式讓這件事從紀律問題變成正確性問題：image tag 由 git tag 決定，
# 而 image 裡的 /openapi.json 印的是 APP_VERSION。兩者不一致的話，
# 線上跑的 v1.2.0 會自稱 1.1.0，追問題的人會被帶到錯的 commit。
set -euo pipefail

# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

readonly CONFIG="apps/api/app/config.py"
readonly CHANGELOG="CHANGELOG.md"

app_version="$(sed -n 's/^APP_VERSION = "\(.*\)"$/\1/p' "$CONFIG")"
if [ -z "$app_version" ]; then
    echo "在 ${CONFIG} 找不到 APP_VERSION = \"...\"" >&2
    exit 1
fi

# 第一個 `## [x.y.z]` 標題就是最新版本（Keep a Changelog 是新的在上面）。
# 中括號內錨在 `[0-9]` 是為了跳過 `## [Unreleased]` —— 日常條目累積在那個標題底下，
# 發版時才改名成版號，所以它不該參與比對。
changelog_version="$(sed -n 's/^## \[\([0-9][^]]*\)\].*/\1/p' "$CHANGELOG" | head -n 1)"
# 一個版號標題都沒有時**不算錯誤**：用這個模板開出來的新專案會把條目清空重寫，
# 在發第一版之前本來就只有 `## [Unreleased]`。底下最後一行會把「沒得比」講出來。
if [ -z "$changelog_version" ]; then
    :
else
    if [ "$app_version" != "$changelog_version" ]; then
        echo "版號不一致：${CONFIG} 是 ${app_version}，${CHANGELOG} 最新版號條目是 ${changelog_version}。" >&2
        echo "升版時兩邊要一起改（見 AGENTS.md「改動後一定要做的事」）。" >&2
        exit 1
    fi
fi

# ── 發版時多一條：git tag 必須是 v$APP_VERSION ──────────────────────────────
#
# 只在 tag build 時檢查。平常的 push／PR 沒有 tag 可比，硬要比的話這支就永遠是紅的。
# GITHUB_REF_TYPE/GITHUB_REF_NAME 由 GitHub Actions 提供；本機執行時兩者都不存在。
if [ "${GITHUB_REF_TYPE:-}" = "tag" ]; then
    tag="${GITHUB_REF_NAME:?GITHUB_REF_TYPE=tag 但沒有 GITHUB_REF_NAME}"
    if [ "$tag" != "v$app_version" ]; then
        echo "git tag 是 ${tag}，但 APP_VERSION 是 ${app_version}（預期 tag 為 v${app_version}）。" >&2
        echo "image 會以 tag 命名，而 image 裡的 OpenAPI 印的是 APP_VERSION —— 兩者必須對得起來。" >&2
        exit 1
    fi
    echo "版號一致：${app_version}（tag ${tag}）"
    exit 0
fi

if [ -n "$changelog_version" ]; then
    echo "版號一致：${app_version}（${CHANGELOG}）"
else
    # 還沒發過第一版，沒有東西可比。講清楚是「沒得比」而不是「一致」，
    # 否則這行會在版號真的對不上的時候一樣印出來。
    echo "APP_VERSION 是 ${app_version}；${CHANGELOG} 還沒有版號條目可以比對。"
fi
