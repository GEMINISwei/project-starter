#!/usr/bin/env bash
#
# 列出所有指令與子指令。
#
# 內容直接讀每支腳本的檔頭: 第一行註解是說明, `#   make …` 開頭的行是子指令。
# 新增指令或子指令時只要寫好檔頭, 不必再維護第二份清單。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

describe() {
    awk '
        NR == 1 && /^#!/ { next }
        /^#[[:space:]]*$/ { next }
        /^#/ { sub(/^#[[:space:]]*/, ""); print; exit }
        { exit }
    ' "$1"
}

echo "用法：make <指令> [子指令]"
for name in "$@"; do
    script="$SCRIPT_DIR/$name.sh"
    echo
    printf '  %s\n' "$(describe "$script")"
    sed -n '/^#   make /s/^#   /    /p' "$script"
done
