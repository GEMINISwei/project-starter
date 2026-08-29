#!/usr/bin/env bash
#
# 安裝主機端的開發相依。
#
# 服務本身跑在容器裡（`make dev`），但 `make lint`／`typecheck`／`test`／`build` 是直接在
# 主機上跑的 —— 那才是編輯器與 CI 看到的環境。這支腳本補上「clone 完到能跑 make check」
# 之間缺的那一步。
set -euo pipefail

cd "$(dirname "$0")/.."

missing=""
command -v uv   >/dev/null 2>&1 || missing="$missing uv"
command -v node >/dev/null 2>&1 || missing="$missing node"
command -v npm  >/dev/null 2>&1 || missing="$missing npm"
if [ -n "$missing" ]; then
    echo "缺少必要工具：$missing" >&2
    echo "uv 見 https://docs.astral.sh/uv/ ；node 與 npm 一起安裝。" >&2
    exit 1
fi

# Node 要落在正確的 major 且不低於下限。**兩個數字來自兩份檔案**，各自只有一個意思：
# major 線在 apps/web/.nvmrc（nvm 與 CI 的 setup-node 讀它；Dockerfile 讀不到，
# 它的 ARG NODE_VERSION 是要手動跟上的第三處），
# 下限在 package.json 的 engines。理由見那份檔案的 `//engines`。
#
# 為什麼把關放在這裡而不是靠 npm 的 engines 檢查：npm 預設只印一行 EBADENGINE
# warning 就繼續裝，而 `engine-strict=true` 會**連帶檢查每個相依套件宣告的 engines**，
# 任何一個第三方套件寫窄了都會擋住安裝 —— 誤傷面太大。這裡只管我們自己訂的那條線。
required_major="$(tr -d '[:space:]' < apps/web/.nvmrc)"
required_min="$(node -p "require('./apps/web/package.json').engines.node.match(/\d+\.\d+\.\d+/)[0]")"
current_node="$(node -v)"
current_version="${current_node#v}"

# 用 sort -V 比版本，不要自己拆 major/minor/patch 再用 `[ -gt ]`：.nvmrc 只寫 major
# （下游改它是預期行為）時拆出來的欄位是空字串，`[ "$x" -gt "" ]` 會變成
# `unary operator expected` —— 結果是用著合法的 Node 卻被擋下，訊息還看不出原因。
lowest="$(printf '%s\n%s\n' "$required_min" "$current_version" | sort -V | head -1)"
if [ "${current_version%%.*}" != "$required_major" ] || [ "$lowest" != "$required_min" ]; then
    echo "Node 版本不符：需要 >=v${required_min} 且 major 為 ${required_major}，目前是 ${current_node}" >&2
    echo "用 nvm 的話：nvm use \"$(cat apps/web/.nvmrc)\"" >&2
    exit 1
fi

# git hooks 掛上來。`core.hooksPath` 是 per-clone 的設定，不會跟著 clone 走，
# 所以它必須由某支腳本來設，而 setup 是唯一一支「clone 完之後一定會跑一次」的。
#
# 已經指到別處時不覆蓋：下游可能自己裝了 husky 之類的東西，而把它的 hooks 換掉
# 是個安靜的破壞 —— 那邊的檢查會從此不再執行，且沒有任何訊息。
current_hooks="$(git config --get core.hooksPath || true)"
if [ -z "$current_hooks" ]; then
    git config core.hooksPath .githooks
    echo "已掛上 .githooks（pre-push 會擋住對 main 的直接 push 與 force push）"
elif [ "$current_hooks" != ".githooks" ]; then
    echo "core.hooksPath 已經指向 ${current_hooks}，不覆蓋。" >&2
    echo "要啟用模板的 pre-push 保護，請自行把 .githooks/pre-push 接進去。" >&2
fi

echo "── apps/api：uv sync ──────────────────────────────────────────────────────"
# --frozen：照 uv.lock 裝，不要順手更新它。相依要升版請明確跑 `uv lock`，
# 否則「跑一次 setup 就默默改了 lock 檔」會在別人的 PR 裡冒出來。
(cd apps/api && uv sync --frozen)

echo "── apps/web：npm ci ───────────────────────────────────────────────────────"
# npm ci 而不是 npm install，理由同上：ci 嚴格照 package-lock.json 裝，對不上就報錯。
(cd apps/web && npm ci)

echo
echo "完成。接著可以跑："
echo "  make check   # lint + typecheck + test + build"
echo "  make dev     # 啟動開發環境（需要 Docker）"
