#!/usr/bin/env bash
#
# 列出所有可用指令。
#
# 說明文字直接抓每支腳本 shebang 之後第一行非空的註解，所以新增指令不必再維護第二份清單。
# 顯示順序由參數決定（Makefile 傳 $(TARGETS) 進來），刻意不排序 —— 讓 TARGETS 保持是
# 唯一的順序來源，相關的指令才能排在一起。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 取第一行非空的註解內容（跳過 shebang 與只有 `#` 的分隔行）。
describe() {
    awk '
        NR == 1 && /^#!/ { next }
        /^#[[:space:]]*$/ { next }
        /^#/ { sub(/^#[[:space:]]*/, ""); print; exit }
        { exit }
    ' "$1"
}

echo "用法：make <指令>"
echo
for name in "$@"; do
    script="$SCRIPT_DIR/$name.sh"
    if [ -f "$script" ]; then
        printf '  %-18s %s\n' "$name" "$(describe "$script")"
    else
        printf '  %-18s %s\n' "$name" "（找不到 scripts/$name.sh）"
    fi
done
echo
echo "每個指令的實作在 scripts/<指令>.sh，也可以不經 make 直接執行。"
