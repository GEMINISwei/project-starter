#!/usr/bin/env bash
#
# 對 scripts/ 與 .githooks/ 底下的 shell 腳本做靜態檢查：shellcheck，外加它抓不到的變數展開那條。
#
# 為什麼需要這支：`make` 的指令實作全部是 shell（見 Makefile 的檔頭），而 shell 是這個 repo
# 裡唯一沒有型別檢查、沒有單元測試的語言 —— `make check` 的 lint／typecheck／test／build
# 一個都碰不到它。而且它出錯的方式最安靜：未加引號的變數在路徑含空白時才裂開、拼錯的變數
# 名展開成空字串（`rm -rf "$prefix/"` 就變成 `rm -rf /`）、`set -e` 在 pipeline 裡不生效。
# 這些都會在某台機器上、某個專案名之下才第一次出現。
#
# `-x` 是必要的：這些腳本靠 `# shellcheck source=` 指示彼此串起來，沒有它 shellcheck 看不到
# lib/ 裡定義的函式與變數，會退化成一堆 SC1091「找不到來源」而不是真的在檢查。
set -euo pipefail

# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

if ! command -v shellcheck >/dev/null 2>&1; then
    # 刻意是錯誤而不是「找不到就跳過」：靜靜跳過的檢查器等於沒有檢查器，
    # 而且會讓「本機綠燈、CI 紅燈」變成常態。CI 的 ubuntu runner 內建 shellcheck。
    echo "找不到 shellcheck。macOS：brew install shellcheck；Debian/Ubuntu：apt-get install shellcheck" >&2
    exit 1
fi

# 檢查對象是全部的 shell 腳本，包含被 source 的 lib/ 與 git hooks。用萬用字元而不是
# 逐一列出：新增一支腳本不該還要記得來這裡登記一次。
#
# hook 特別需要被檢查：它沒有副檔名、平常不會被執行到，而且它是唯一一支**壞掉會放行**
# 的腳本。語法錯誤還算安全（git 收到非零，push 被擋）；真正危險的是邏輯寫錯讓那個
# while 迴圈一次都沒進去 —— 那時它安靜地回 0，push 照過，不會有任何訊息。
shellcheck -x scripts/*.sh scripts/lib/*.sh .githooks/*

# 還有一條 shellcheck 抓不到：`"$VAR中文"`。
# （這行刻意不以 shellcheck 開頭 —— 那樣會被當成 directive 解析而報 SC1073。）
#
# bash 3.2 —— 也就是 macOS 內建的那支 —— 會把後面的多位元組字元吃進變數名，於是
# `set -u` 當場報 `app_version�: unbound variable`。bash 5（CI 與 Linux 主機）沒這個
# 問題，所以它只在開發者的 Mac 上出現，而且**最常中的是錯誤路徑**：需要那行訊息告訴你
# 哪裡不對的時候，拿到的是一句看不懂的 unbound variable。寫成 `${VAR}` 就沒事。
#
# LC_ALL=C 是必要的：要判斷「後面那個 byte 是不是 ASCII」，就得讓 awk 按 byte 讀。
# 不指定的話 CI 的 gawk 在 UTF-8 locale 下會把中文當成一個可列印字元而全部放行，
# 於是這支檢查在唯一會出事的平台以外都是綠的。
offenders="$(LC_ALL=C awk '
    /^[[:space:]]*#/ { next }
    {
        rest = $0
        while (match(rest, /\$[A-Za-z_][A-Za-z0-9_]*/)) {
            tail = substr(rest, RSTART + RLENGTH, 1)
            if (tail != "" && tail !~ /[[:print:][:blank:]]/) {
                printf "%s:%d: %s\n", FILENAME, FNR, $0
                next
            }
            rest = substr(rest, RSTART + RLENGTH)
        }
    }
' scripts/*.sh scripts/lib/*.sh .githooks/*)"

if [ -n "$offenders" ]; then
    echo "變數後面直接接了多位元組字元，在 macOS 的 bash 3.2 會變成 unbound variable。" >&2
    echo "請改寫成 \${VAR}：" >&2
    printf '%s\n' "$offenders" >&2
    exit 1
fi

echo "shell 腳本靜態檢查通過（含 \$VAR 後接多位元組字元）"
