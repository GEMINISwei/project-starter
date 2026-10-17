#!/usr/bin/env bash
#
# 從 repo 的 environment 名稱挑出這次要部署的那一組: deploy-targets.sh <組名> < 名稱清單
#
# 組名 = environment 名稱第一個 `-` 之前的部分: production 組是 `production` 與 `production-*`。
# 名稱一行一個從 stdin 讀進來 (deploy.yml 從 GitHub API 取得), 符合的照字母順序一行一個輸出。
#
# 不用 `production*` 的萬用比對: 那會把 `productionx` 也算進來。比對不分大小寫, 跟 GitHub 一樣。
# 一個都沒有就列出現有的組並失敗: 打錯組名不能變成「部署了零套, 結果是綠的」。
#
# 要能在 macOS 內建的 bash 3.2 跑 (make check 的測試在本機執行), 所以不用 ${var,,} 與 mapfile。
set -euo pipefail

target="${1:-}"
# 組名也是 image 的標籤 (ghcr.io/...-api:<組名>), 所以只收標籤合法、而且不含分隔字元 `-` 的寫法。
if ! [[ "${target}" =~ ^[a-z0-9][a-z0-9_.]*$ ]]; then
    echo "組名格式不對：「${target}」（小寫英數與 . _，例如 production、staging）" >&2
    exit 1
fi

matched=()
groups=()
while IFS= read -r name || [ -n "${name}" ]; do
    [ -n "${name}" ] || continue
    lower="$(printf '%s' "${name}" | tr '[:upper:]' '[:lower:]')"
    group="${lower%%-*}"
    groups+=("${group}")
    if [ "${group}" = "${target}" ]; then
        matched+=("${name}")
    fi
done

if [ "${#matched[@]}" -eq 0 ]; then
    if [ "${#groups[@]}" -eq 0 ]; then
        echo "repo 還沒有任何 environment，請先在 Settings → Environments 建立（例如 production）" >&2
    else
        available="$(printf '%s\n' "${groups[@]}" | LC_ALL=C sort -u | paste -sd ' ' -)"
        echo "找不到「${target}」這一組的 environment，現有的組：${available}" >&2
    fi
    exit 1
fi

printf '%s\n' "${matched[@]}" | LC_ALL=C sort
