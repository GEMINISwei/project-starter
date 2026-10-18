#!/usr/bin/env bash
#
# 啟動服務: make start (依 .env 的 MODE)
#
#   make start   啟動 postgres → migrate → api → web → nginx (會自動跑 migration); production 會重新建置或拉 image
#
# development 用 bind mount 的原始碼, 改了直接生效, 不必建置。
#
# production 預設 `--build`: 要確定跑的是目前這份原始碼建出來的 image。shell 有匯出 API_IMAGE 與
# WEB_IMAGE 時改成從 registry 拉 (deploy workflow 走這條, 見 docs/operations.md〈自動部署〉), 而且
# **不能帶 `--build`**: 實測 `--build` 會蓋過 `pull_policy: always`, 照樣在主機上建置, 還把建出來的
# 東西標成 registry 的 image 名稱。兩個要一起給 —— 只給一個的話, 另一個會去 Docker Hub 拉
# `<專案>-web:latest` 之類不存在的 image。
set -euo pipefail

# shellcheck source=scripts/lib/compose.sh
source "$(dirname "$0")/lib/compose.sh"

usage() {
    sed -n '/^#   make start/s/^#   //p' "$0" >&2
    exit 1
}

# 正式環境只從發版的 tag 啟動: 主機上 `git pull` 了 main 再啟動, 等於上線一份沒發版、沒經過 CI
# 的程式碼。比對 tag 指到的 commit 而不是 `git describe`: 同一個 commit 可能有好幾個 tag。
require_release_checkout() {
    local version tagged head
    version="$(app_version)"
    tagged="$(git rev-parse --quiet --verify "refs/tags/v${version}^{commit}" 2> /dev/null || true)"
    head="$(git rev-parse --quiet --verify HEAD 2> /dev/null || true)"
    if [ -z "${tagged}" ] || [ "${tagged}" != "${head}" ]; then
        echo "正式環境只能從發版的 tag 啟動：HEAD 要停在 v${version}" >&2
        echo "  git fetch --tags && git checkout v${version}" >&2
        exit 1
    fi
}

[ "$#" -eq 0 ] || usage
load_env
require_env COMPOSE_PROJECT_NAME
require_mode

if [ "${MODE}" = development ]; then
    app_compose up -d --remove-orphans
else
    require_release_checkout
    if [ -n "${API_IMAGE:-}${WEB_IMAGE:-}" ]; then
        require_env API_IMAGE WEB_IMAGE
        IMAGE_PULL_POLICY=always app_compose up -d --remove-orphans
    else
        app_compose up -d --build --remove-orphans
    fi
fi
echo "已啟動：http://localhost:${SYSTEM_PORT}"
