#!/usr/bin/env bash
#
# 確認版號三者一致：APP_VERSION、CHANGELOG 的最新版號條目、發版時的 git tag。
#
# 這支存在的理由：`APP_VERSION` 與變更紀錄是下游判斷「落後多少、同步要做什麼」的依據
# （見 docs/downstream.md），而三者對不上是**沒有症狀**的：CI 的 pr-checks
# 只擋「有沒有寫條目」，擋不到「條目的版號跟程式裡的版號對不起來」。
#
# registry 模式讓這件事從紀律問題變成正確性問題：image tag 由 git tag 決定，
# 而 image 裡的 /openapi.json 印的是 APP_VERSION。兩者不一致的話，
# 線上跑的 v1.2.0 會自稱 1.1.0，追問題的人會被帶到錯的 commit。
set -euo pipefail

# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

readonly CONFIG="apps/api/app/config.py"
readonly TEMPLATE_CHANGELOG="CHANGELOG.template.md"

# 「這個 repo 的變更紀錄是哪一份」取決於它是模板還是下游，而 APP_VERSION 在兩邊
# 記的是不同東西的版號（模板的模板版 vs 下游的產品版）。
#
# 判準用 TEMPLATE.md 在不在，**不要用 `git remote` 有沒有 template** ——
# remote 是本機設定，下游 CI 的 checkout 上根本不存在，那樣判會在 CI 上永遠判成模板、
# 比對到一份下游不會去改的檔案，而且是綠的（看不出判錯）。
# TEMPLATE.md 是 in-tree 的，導入完成就刪掉，生命週期在 docs/downstream.md 有定義。
if [ -f TEMPLATE.md ]; then
    CHANGELOG="$TEMPLATE_CHANGELOG"
else
    CHANGELOG="CHANGELOG.md"
fi
readonly CHANGELOG

app_version="$(sed -n 's/^APP_VERSION = "\(.*\)"$/\1/p' "$CONFIG")"
if [ -z "$app_version" ]; then
    echo "在 ${CONFIG} 找不到 APP_VERSION = \"...\"" >&2
    exit 1
fi

# 第一個 `## [x.y.z]` 標題就是最新版本（Keep a Changelog 是新的在上面）。
# 中括號內錨在 `[0-9]` 是為了跳過 `## [Unreleased]` —— 日常條目累積在那個標題底下，
# 發版時才改名成版號，所以它不該參與比對。
changelog_version="$(sed -n 's/^## \[\([0-9][^]]*\)\].*/\1/p' "$CHANGELOG" | head -n 1)"
if [ -z "$changelog_version" ]; then
    # 下游還沒發過第一版時，這是正常狀態而不是錯誤 —— 種子檔裡只有 `## [Unreleased]`。
    # 模板自己不可能落到這裡（它的紀錄從 0.0.1 開始），所以那邊仍然是硬錯誤。
    if [ "$CHANGELOG" != "$TEMPLATE_CHANGELOG" ]; then
        : # 底下最後一行會把「沒得比」講出來，這裡不要先講一次
    else
        echo "在 ${CHANGELOG} 找不到任何 '## [x.y.z]' 標題" >&2
        exit 1
    fi
else
    if [ "$app_version" != "$changelog_version" ]; then
        echo "版號不一致：${CONFIG} 是 ${app_version}，${CHANGELOG} 最新版號條目是 ${changelog_version}。" >&2
        echo "升版時兩邊要一起改（見 AGENTS.md「改動後一定要做的事」）。" >&2
        # 下游忘了刪 TEMPLATE.md 的話會被判成模板，於是拿自己的產品版號去比對上游的紀錄 ——
        # 上面那行訊息完全看不出是判錯了對象，所以在這裡把判準講出來。
        if [ "$CHANGELOG" = "$TEMPLATE_CHANGELOG" ]; then
            echo "（這個 repo 被判定為模板本身，判準是 TEMPLATE.md 還在。" >&2
            echo "  這裡其實是下游專案的話，導入完成就該刪掉 TEMPLATE.md，見 docs/downstream.md。）" >&2
        fi
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
    # 只有下游走得到這裡：還沒發過第一版，沒有東西可比。講清楚是「沒得比」而不是「一致」，
    # 否則這行會在版號真的對不上的時候一樣印出來。
    echo "APP_VERSION 是 ${app_version}；${CHANGELOG} 還沒有版號條目可以比對。"
fi
