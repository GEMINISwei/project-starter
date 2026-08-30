#!/usr/bin/env bash
#
# 確認文件指到的檔案、錨點與識別字真的存在，且指令表涵蓋每一支 check-*。
#
# 只查五種**機械上可判定**的東西，語意正不正確仍然靠 review：
#   1. 路徑：markdown 連結目標，與反引號裡含 `/` 的路徑。
#   2. 錨點：連結目標 `#` 之後那一段，比對目標文件的標題。
#   3. 帶點的識別字（`Xxx.yyy`，擁有者是大寫開頭）。
#   4. 目錄樹：`<!-- check-docs: tree <base> -->` 標記的圍欄區塊，逐項照縮排接回祖先驗證。
#      沒有標記卻長得像樹的區塊會直接報錯 —— 圍欄整段跳過，所以沒標記的樹是零覆蓋。
#      形狀示範用 `tree -` 明確豁免。
#   5. 指令表：`<!-- check-docs: commands <前綴> -->` 標記的表格，要恰好列出 Makefile
#      `TARGETS` 裡該前綴的每一個目標。這條是反方向的：漏掉一整支檢查器不會讓任何東西失敗，
#      只是沒有人知道它在，而它守的東西就此無人聞問。
#
# **標記一律要獨佔一行**（regex 錨在行首）。散文裡用反引號提到標記不算數 —— 不錨的話「同一行
# 同時提到 ignore-start 與 ignore-end」會把 ignoring 打開卻永遠關不掉，那一行之後整份文件零覆蓋。
#
# 圍欄程式碼區塊（```）整段跳過：教學裡的 `modules/products/` 是刻意的假想範例。
# CHANGELOG.md 不掃 —— 已發布的條目是當時的紀錄，不該為了讓檢查器過而竄改。
#
# 整段跳過還有第二種寫法：`<!-- check-docs: ignore-start --> … <!-- check-docs: ignore-end -->`。
# 用它之前先確認你要的不是**修文件** —— 它只為了一種情況存在：那段文字的主題就是某些檔案的
# 不存在（移除模組的清單）。
set -euo pipefail

# shellcheck source=scripts/lib/common.sh
source "$(dirname "$0")/lib/common.sh"

DOCS=(README.md AGENTS.md docs/*.md contracts/README.md)
# TEMPLATE.md 導入後會被刪掉，還在的時候才掃。
[ -f TEMPLATE.md ] && DOCS+=(TEMPLATE.md)

# 行內出現、但不指向 repo 內任何東西的字串。**每一條都要附理由。**
# 比照 apps/web/knip.ts 與 apps/api/pyproject.toml 的 per-file-ignores 慣例。
ALLOW=(
    # `make e2e` 失敗時才產生的檔案（scripts/e2e.sh 的 teardown 倒容器 log 進去），
    # 而且進 .gitignore。文件非指名它不可 —— stack 起不來時它是唯一講得出原因的東西，
    # 說成「test-results 裡的某個 log」等於沒說。
    "e2e/test-results/docker-logs.txt"
    # 佔位檔名，用來說明「每個對話框各自一個檔」的命名慣例。
    "CreateXxxDialog.tsx"
    "EditXxxDialog.tsx"
    # Next 16 之前的舊檔名，出現在「proxy.ts 不能搬」那段的說明裡。
    "middleware.ts"
    # 外部 Design System 產出的落地處。只有實際導入 DS 的專案才會有這個目錄，
    # 模板本身沒有 —— 但導入步驟必須寫在文件裡（docs/design-system.md）。
    "apps/web/app/tokens/vendor/"
    # CodeQL 的 advanced setup 會產生的 workflow。**這個 repo 刻意不要它** ——
    # 文件裡指名它是為了說明「為什麼選 default setup」（那份 workflow 會被下游繼承，
    # 而 code scanning 對 private repo 要付費，繼承過去就是一個固定紅的 job）。
    ".github/workflows/codeql.yml"
    # 還不存在的第二份契約，出現在命名規則的示範中。
    "ws-asyncapi.json"
    "api-asyncapi.json"
    # 「為什麼不收成這個目錄」的假想結構，出現在 config/ 與 app/ 分開的理由裡。
    "app/_config/"
    # 教學裡新增模組時的假想目標名稱。
    "modules/products/"
    # Next 的建置產物，只在 `npm run build` 之後存在，永遠不會進版控。
    # 文件裡指到它是為了說明 UPLOAD_SIZE_LIMIT 為什麼移不到執行期（docs/operations.md）。
    # 注意這一條**非加不可**：`path_exists` 會試 `apps/web/` 當基準，所以在建置過的
    # 工作樹上它「存在」，本機跑就是綠的 —— 只有乾淨 checkout 的 CI 會紅。
    ".next/required-server-files.json"
)

is_allowed() {
    local candidate="$1" allowed
    for allowed in "${ALLOW[@]}"; do
        [ "$candidate" = "$allowed" ] && return 0
    done
    return 1
}

# 路徑候選：先試文件自己的目錄（markdown 連結是相對於它的），再試 repo 根、`apps/`
# （移除模組的表格用 `web/…`／`api/…` 當縮寫）與兩個 app 根（`modules/users/model.py`
# 這種寫法省略了 apps/api/ 前綴）。
path_exists() {
    local doc_dir="$1" candidate="$2" base
    # 空字串要擋下來：`[ -e "$base/" ]` 永遠成立，解析一旦壞掉會**安靜地放行**。
    # 比照底下「收集不到任何識別字就當檢查器本身壞了」的處理。
    [ -n "$candidate" ] || return 1
    for base in "$doc_dir" . apps apps/web apps/api; do
        [ -e "$base/$candidate" ] && return 0
    done
    return 1
}

# 原始碼裡的名字，掃一次收進兩份清單：`DEFINED`（這個 repo 自己定義的）與
# `SEEN`（出現過的任何識別字）。
#
# 名稱只收集一次，再以固定字串逐行比對，避免 macOS 與 CI 的 grep 方言造成結果差異。
SRC_DIRS=(apps/api apps/web/shared apps/web/modules apps/web/config)

collect_names() {
    # 先 prune 再挑檔案。少了這一步 `apps/api/.venv/` 會整包被掃進來，而那裡有九個
    # 第三方的 `class Response:` —— 一個早就不存在的 `Response.WsEvent` 會因此判定為存在，
    # 檢查器安靜地永遠綠燈。這是這支腳本最容易壞而且壞了看不出來的地方。
    # shellcheck disable=SC2016 # awk 程式要單引號，`$0`／`$1` 是 awk 的欄位不是 shell 的
    find "${SRC_DIRS[@]}" \
        \( -name '.venv' -o -name 'node_modules' -o -name '__pycache__' \
           -o -name '.next' -o -name '.*_cache' -o -name 'coverage' \) -prune -o \
        -type f \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' \) -print0 \
    | xargs -0 awk '
        {
            # 定義：class／def／type／interface／enum／const／function 後面接的那個名字。
            if (match($0, /(^|[^A-Za-z0-9_])(class|def|type|interface|enum|const|function)[ \t]+[A-Za-z_][A-Za-z0-9_]*/)) {
                frag = substr($0, RSTART, RLENGTH)
                n = split(frag, parts, /[ \t]+/)
                defined[parts[n]] = 1
            }
            # 出現過的所有識別字（成員名用這份查就夠 —— 成員可能是方法、欄位或 enum 成員，
            # 它們的宣告形式各不相同，硬要分辨只會讓規則變得可疑）。
            rest = $0
            while (match(rest, /[A-Za-z_][A-Za-z0-9_]*/)) {
                seen[substr(rest, RSTART, RLENGTH)] = 1
                rest = substr(rest, RSTART + RLENGTH)
            }
        }
        END {
            for (n in defined) print "D\t" n
            for (n in seen)    print "S\t" n
        }
    '
}

NAME_DIR="$(mktemp -d)"
trap 'rm -rf "$NAME_DIR"' EXIT
collect_names | awk -F'\t' -v dir="$NAME_DIR" '
    $1 == "D" { print $2 > (dir "/defined") }
    $1 == "S" { print $2 > (dir "/seen") }
'
# 一個名字都沒收到，代表 find／awk 這條管線壞了。這時候「全部通過」是最危險的結果，
# 所以當成失敗處理，而不是安靜地放行。
[ -s "$NAME_DIR/defined" ] || { echo "收集不到任何識別字，檢查器本身壞了" >&2; exit 1; }

identifier_exists() {
    local owner="${1%%.*}" member="${1##*.}"
    grep -Fxq -- "$owner"  "$NAME_DIR/defined" || return 1
    grep -Fxq -- "$member" "$NAME_DIR/seen"    || return 1
    return 0
}

# 標題轉成錨點，規則跟 GitHub 一樣：去掉標點、小寫、空白換連字號（中文原樣保留）。
#
# 標點分兩批刪，**不能合併成一個否定字元集**（`[^[:alnum:][:space:]-]` 那種寫法）：
# awk 在 C locale 下把多位元組字元當成一串 byte，中文字的每個 byte 都不是 alnum，
# 否定集會把整個標題削光。改用 `[[:punct:]]` —— 它在 C locale 只涵蓋 ASCII，
# 多位元組的 byte 一個都不會中 —— 再對全形標點逐個 gsub 補上。
#
# 兩批一起下的理由是**讓兩種 awk 得到同一個答案**：CI 的 gawk 在 UTF-8 locale 下
# `[[:punct:]]` 已經吃掉全形標點，macOS 的 awk 不會。少了下面那串，同一份文件會本機綠燈、
# CI 紅燈（或反過來）。全形那串是列舉的，用到沒列進去的符號時 slug 會對不上而**報錯**，
# 不是安靜放行 —— 修法是把它加進那一行。
heading_slugs() {
    awk '
        /^[[:space:]]*```/ { fenced = !fenced; next }
        fenced { next }
        /^#+[[:space:]]/ {
            s = $0
            sub(/^#+[[:space:]]+/, "", s)
            # 連字號要保留，先移開再讓 [[:punct:]] 掃過。
            gsub(/-/, "\036", s)
            gsub(/[[:punct:]]/, "", s)
            gsub(/：/, "", s); gsub(/，/, "", s); gsub(/、/, "", s)
            gsub(/（/, "", s); gsub(/）/, "", s)
            gsub(/「/, "", s); gsub(/」/, "", s)
            gsub(/？/, "", s); gsub(/！/, "", s); gsub(/；/, "", s)
            gsub(/—/, "", s);  gsub(/…/, "", s)
            gsub(/\036/, "-", s)
            sub(/^[[:space:]]+/, "", s)
            sub(/[[:space:]]+$/, "", s)
            gsub(/[[:space:]]/, "-", s)
            print tolower(s)
        }
    ' "$1"
}

# 錨點候選長 `path#frag`，path 為空代表同一份文件。回傳解析到的檔案。
anchor_file() {
    local doc="$1" rel="${2%%#*}" base
    [ -n "$rel" ] || { printf '%s\n' "$doc"; return 0; }
    for base in "$(dirname "$doc")" . apps apps/web apps/api; do
        [ -f "$base/$rel" ] && { printf '%s\n' "$base/$rel"; return 0; }
    done
    return 1
}

anchor_exists() {
    local doc="$1" candidate="$2" file slugs
    # 路徑本身不存在時放行：同一行的 path 那筆已經會報，這裡再報一次只是噪音。
    file="$(anchor_file "$doc" "$candidate")" || return 0
    # 錨點只在 markdown 上有意義。指到別種檔案的 `#…` 是行號或片段語法，不驗證。
    case "$file" in *.md) ;; *) return 0 ;; esac
    # 先接成字串再比對，**不要寫成 `heading_slugs … | grep -Fxq`**：`grep -q` 一命中就結束，
    # 上游的 awk 因此收到 SIGPIPE 而以 141 結束，`pipefail` 會把整條管線判成失敗 ——
    # 也就是「錨點存在」被回報成「錨點不存在」。而且它跟文件長度有關：標題少的時候
    # 東西全進了管線緩衝區、awk 早就寫完，症狀不會出現。文件長到超過緩衝區才開始紅，
    # 屆時看起來會像是那次改標題改壞了。
    slugs="$(heading_slugs "$file")"
    grep -Fxq -- "${candidate#*#}" <<< "$slugs"
}

# 抽出候選，輸出 `行號<TAB>種類<TAB>候選`。圍欄區塊內的行整段跳過。
extract() {
    awk '
        /^[[:space:]]*<!--[[:space:]]*check-docs:[[:space:]]*ignore-start[[:space:]]*-->/ { ignoring = 1; next }
        /^[[:space:]]*<!--[[:space:]]*check-docs:[[:space:]]*ignore-end[[:space:]]*-->/   { ignoring = 0; next }
        ignoring { next }
        # 樹狀圖：`<!-- check-docs: tree <base> -->` 標記的下一個圍欄區塊要逐項驗證。
        # 縮排代表層級，所以要把祖先接回來 —— `main.py` 在 `apps/api/` 底下。
        /^[[:space:]]*<!--[[:space:]]*check-docs:[[:space:]]*tree[[:space:]]/ {
            if (match($0, /tree[[:space:]]+[^[:space:]]+/)) {
                pending = substr($0, RSTART, RLENGTH)
                sub(/^tree[[:space:]]+/, "", pending)
            }
            next
        }
        /^[[:space:]]*```/ {
            if (fenced) { fenced = 0; tree = ""; warned = 0 }
            else { fenced = 1; tree = pending; pending = ""; delete stack }
            next
        }
        # 沒有標記卻長得像樹 —— 報出來，讓作者選：加 `tree <base>` 驗證它，
        # 或加 `tree -` 說明這是形狀示範。
        fenced && tree == "" && (index($0, "├──") > 0 || index($0, "└──") > 0) {
            if (!warned) print NR "\tuntagged-tree\t-"
            warned = 1
            next
        }
        fenced && tree != "" && tree != "-" {
            line = $0
            # 畫樹的四個字元先換成 ASCII，之後所有位置運算都在純 ASCII 上做。
            # 因為 awk 的 index()／substr() 用 byte 還是**字元**計數取決於實作與 locale：
            # macOS 的 onetrue awk 算 byte，CI 的 awk 算字元。寫死「`├──` 佔 9 byte」在後者
            # 會多吃 6 個字元，把 `manifest.py` 讀成 `est.py`，症狀是本機綠燈、CI 紅燈。
            # 換成單 byte 的 ASCII 之後兩種語意得到同一個答案，`│` 換成空白也維持了
            # 「每層 4 格」的縮排（層級算錯的結果是把路徑接到別的祖先底下）。
            gsub(/│/, " ", line)
            gsub(/├/, "|", line)
            gsub(/└/, "|", line)
            gsub(/─/, "-", line)
            branch = index(line, "|")
            if (branch == 0) next
            depth = int((branch - 1) / 4)
            # 接在後面的破折號用 regex 吃掉，這樣「幾個 `─`」也不必假設。
            entry = substr(line, branch + 1)
            sub(/^-+[[:space:]]*/, "", entry)
            sub(/[[:space:]].*$/, "", entry)
            if (entry == "") next
            stack[depth] = entry
            # 花括號展開、`<name>` 佔位與萬用字元不是真路徑，只記層級不驗證。
            if (entry ~ /[{}<>*]/) next
            full = tree
            for (level = 0; level <= depth; level += 1) {
                item = stack[level]
                sub(/\/$/, "", item)
                full = (full == "" || full == ".") ? item : full "/" item
            }
            print NR "\tpath\t" full
            next
        }
        fenced { next }
        {
            line = $0

            # markdown 連結目標：](target)。外部連結不看。
            # 路徑與錨點分開輸出：`docs/x.md#某節` 產生 path 與 anchor 兩筆；
            # 同一份文件內的 `#某節` 只有 anchor 那一筆，path 部分留空由驗證端補成當前檔。
            rest = line
            while (match(rest, /\]\([^)]+\)/)) {
                target = substr(rest, RSTART + 2, RLENGTH - 3)
                rest = substr(rest, RSTART + RLENGTH)
                if (target ~ /^(https?:|mailto:)/) continue
                frag = ""
                if (index(target, "#") > 0) {
                    frag = substr(target, index(target, "#") + 1)
                    target = substr(target, 1, index(target, "#") - 1)
                }
                if (target != "") print NR "\tpath\t" target
                if (frag != "")   print NR "\tanchor\t" target "#" frag
            }

            # 反引號內容。
            rest = line
            while (match(rest, /`[^`]+`/)) {
                token = substr(rest, RSTART + 1, RLENGTH - 2)
                rest = substr(rest, RSTART + RLENGTH)

                # 路徑：含 `/`，且有副檔名或以 `/` 結尾。前後的雜訊先剝掉。
                sub(/^\.\//, "", token)
                if (token ~ /^[A-Za-z0-9_.@()\[\]-]+(\/[A-Za-z0-9_.*@()\[\]-]+)+\/?$/ &&
                    (token ~ /\.[a-z]+$/ || token ~ /\/$/)) {
                    if (token !~ /[*]/) print NR "\tpath\t" token
                    continue
                }

                # 帶點的識別字：擁有者大寫開頭、單層點。文件寫函式時慣例帶 `()`，先剝掉。
                # 副檔名結尾的是檔名不是識別字（`CLAUDE.md`、`knip.ts`），
                # 那類沒有路徑就無從查起，交給 review。
                sub(/\(\)$/, "", token)
                if (token ~ /^[A-Z][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$/ &&
                    token !~ /\.(md|ts|tsx|py|css|json|mjs|js|sh|yml|lock|toml|example)$/)
                    print NR "\tident\t" token
            }
        }
    ' "$1"
}

# 指令表的雙向比對。**兩個方向都要**：少列一支是「檢查器存在但沒人知道」，
# 多列一支是「文件教一個已經被刪掉的指令」，後者在下游移除 CD 之後就會發生。
#
# 用標記而不是認表格的標題文字（「原始碼外的檢查」那一格）：標題是會被改寫的散文，
# 綁上去的話改個措辭就讓這支檢查器安靜地什麼都不驗 —— 而那正是它要防的事。
COMMAND_DOC="docs/development.md"

# Makefile 的 `TARGETS` 是續行的，所以要一路讀到沒有結尾反斜線的那一行為止。
makefile_targets() {
    awk '
        /^TARGETS[[:space:]]*=/ { collecting = 1 }
        collecting {
            line = $0
            sub(/^TARGETS[[:space:]]*=/, "", line)
            more = (line ~ /\\$/)
            sub(/\\$/, "", line)
            n = split(line, parts, /[[:space:]]+/)
            for (i = 1; i <= n; i += 1) if (parts[i] != "") print parts[i]
            if (!more) exit
        }
    ' Makefile
}

# 標記之後的那個表格裡，所有 `make <name>` 的 name。表格結束（第一行不以 | 開頭的
# 非空行）就停 —— 標記只管緊接著的那一個表格。
documented_commands() {
    awk '
        /^[[:space:]]*<!--[[:space:]]*check-docs:[[:space:]]*commands[[:space:]]/ { seeking = 1; next }
        seeking && /^\|/ {
            in_table = 1
            rest = $0
            while (match(rest, /`make [a-z0-9-]+`/)) {
                # `make x` → 去掉前後反引號與 "make "：前綴 6 字元、尾巴 1 字元。
                print substr(rest, RSTART + 6, RLENGTH - 7)
                rest = substr(rest, RSTART + RLENGTH)
            }
            next
        }
        in_table { exit }
    ' "$1"
}

command_marker_prefix() {
    awk '
        match($0, /^[[:space:]]*<!--[[:space:]]*check-docs:[[:space:]]*commands[[:space:]]+[^[:space:]]+/) {
            marker = substr($0, RSTART, RLENGTH)
            sub(/.*commands[[:space:]]+/, "", marker)
            print marker
            exit
        }
    ' "$1"
}

check_command_table() {
    local prefix expected actual missing stale
    # 下游可能不留這份文件；沒有就沒有要守的東西。有檔案卻沒有標記則是失敗 ——
    # 「標記不見了」與「表格是對的」不能是同一個結果。
    [ -f "$COMMAND_DOC" ] || return 0

    prefix="$(command_marker_prefix "$COMMAND_DOC")"
    if [ -z "$prefix" ]; then
        echo "${COMMAND_DOC}: 找不到 <!-- check-docs: commands <前綴> --> 標記。" >&2
        echo "  請把它加回列出 make 指令的那個表格前面，否則沒有人在守「新增指令卻沒寫進文件」。" >&2
        return 1
    fi

    expected="$(makefile_targets | grep "^${prefix}" | sort)"
    actual="$(documented_commands "$COMMAND_DOC" | grep "^${prefix}" | sort -u)"

    # 一個都收不到代表解析壞了，這時「全部通過」是最危險的結果（同上面收集識別字那段）。
    if [ -z "$expected" ]; then
        echo "Makefile 的 TARGETS 裡找不到任何 ${prefix}* 目標，檢查器本身壞了" >&2
        return 1
    fi

    missing="$(comm -23 <(printf '%s\n' "$expected") <(printf '%s\n' "$actual"))"
    stale="$(comm -13 <(printf '%s\n' "$expected") <(printf '%s\n' "$actual"))"
    [ -z "$missing" ] && [ -z "$stale" ] && return 0

    echo "${COMMAND_DOC}: 指令表與 Makefile 的 TARGETS 對不上（前綴 ${prefix}）：" >&2
    [ -n "$missing" ] && echo "  Makefile 有、文件沒列到：$(tr '\n' ' ' <<< "${missing}")" >&2
    [ -n "$stale" ]   && echo "  文件列了、Makefile 沒有：$(tr '\n' ' ' <<< "${stale}")" >&2
    return 1
}

command_table_failed=0
check_command_table || command_table_failed=1

failed=0
for doc in "${DOCS[@]}"; do
    [ -f "$doc" ] || continue
    doc_dir="$(dirname "$doc")"

    while IFS=$'\t' read -r lineno kind candidate; do
        is_allowed "$candidate" && continue

        case "$kind" in
            path)
                path_exists "$doc_dir" "$candidate" \
                    || { echo "$doc:$lineno: 指向不存在的路徑：$candidate" >&2; failed=1; }
                ;;
            anchor)
                anchor_exists "$doc" "$candidate" || {
                    echo "$doc:$lineno: 指向不存在的錨點：$candidate" >&2
                    echo "  目標文件實際有的錨點：" >&2
                    heading_slugs "$(anchor_file "$doc" "$candidate")" | sed 's|^|    #|' >&2
                    failed=1
                }
                ;;
            ident)
                identifier_exists "$candidate" \
                    || { echo "$doc:$lineno: 指向不存在的識別字：$candidate" >&2; failed=1; }
                ;;
            untagged-tree)
                echo "$doc:$lineno: 這個圍欄區塊是目錄樹，但沒有 check-docs 標記。" >&2
                echo "  加 <!-- check-docs: tree <base> --> 逐項驗證路徑，" >&2
                echo "  或加 <!-- check-docs: tree - --> 表示這棵樹是形狀示範、不對應真實檔案。" >&2
                failed=1
                ;;
        esac
    done < <(extract "$doc")
done

if [ "$failed" -ne 0 ]; then
    echo >&2
    echo "文件與實際對不上。請修文件；刻意的假想範例移進圍欄程式碼區塊／ALLOW，樹狀圖見上面的訊息。" >&2
fi

if [ "$failed" -ne 0 ] || [ "$command_table_failed" -ne 0 ]; then
    exit 1
fi

echo "文件指向的路徑、錨點與識別字都存在，目錄樹與指令表也都對得上"
