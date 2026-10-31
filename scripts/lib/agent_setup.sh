#!/usr/bin/env bash
#
# 開發機的 AI agent 協作環境: make init dev 呼叫 (make init prod 不用, 部署主機不跑 agent)。
#
# docs/extending/agent-hooks.md〈啟用與停用〉的每一項, 少了都不會報錯, 只是那一層檢查安靜地不生效,
# 所以能在開案時判斷的就在這裡擋下或提醒。Claude 與 Codex 的 /hooks 確認記在各自的內部設定,
# 讀不到, 只能在最後印出來提醒。
#
# 被 source 的檔案, 理由同 common.sh 不寫 `set -euo pipefail`。

[ -n "${AGENT_SETUP_SH_LOADED:-}" ] && return 0
AGENT_SETUP_SH_LOADED=1

# hook 直接用 PATH 上的 python3 執行, 不經過 api 的虛擬環境; macOS 內建的 3.9 就夠。
# 沒有的話 Claude 只顯示 hook 錯誤、照常執行指令, 守衛等於不存在。
require_python3() {
    if ! command -v python3 > /dev/null 2>&1; then
        echo "缺少 python3：AI agent 的 hook 用它執行（3.9 以上，macOS 內建的即可）。" >&2
        exit 1
    fi
    if ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
        echo "python3 版本太舊：AI agent 的 hook 需要 3.9 以上，目前是 $(python3 --version 2>&1)。" >&2
        exit 1
    fi
}

# Windows 沒開 core.symlinks 時, git 把 symlink 寫成內容是目標路徑的一般檔案, Claude 讀不到任何 skill。
# make check 也會擋 (tests/test_agent_skills.py), 但等到那時已經裝完一輪相依。
# 完全不存在時不擋: 不用 Claude 的專案可能刻意刪掉 .claude/, 不該因此永遠 init 不了。
require_skills_symlink() {
    [ -e .claude/skills ] || [ -L .claude/skills ] || return 0
    [ -L .claude/skills ] && [ -d .claude/skills ] && return 0
    echo ".claude/skills 不是指向 .agents/skills 的 symlink，Claude 會讀不到任何 skill。修正：" >&2
    echo "    git config core.symlinks true   # Windows 另外要開啟開發人員模式" >&2
    echo "    rm -rf .claude/skills && git checkout -- .claude/skills" >&2
    exit 1
}

# 裝了 Codex 卻還沒信任這個專案時, 專案的 .codex/ (hook、rules、AI_AGENT) 都不會載入。
# 只提醒: 不是每個人都用 Codex。信任狀態記在 Codex 設定的 [projects."<路徑>"] trust_level。
remind_codex_trust() {
    command -v codex > /dev/null 2>&1 || return 0
    codex_trusts_project "${CODEX_HOME:-$HOME/.codex}/config.toml" "$(pwd -P)" && return 0
    echo "⚠️  Codex 還沒信任這個專案：在專案目錄執行 codex 並選擇信任，再用 /hooks 確認每個 hook。"
    echo "   沒信任時專案的 hook、rules 與 AI_AGENT 都不會載入，也不會報錯。"
}

# Codex 設定裡 [projects."<root>"] 那一節有沒有 trust_level = "trusted"。
# 只用 bash 內建的功能逐行讀: 不必為了一個判斷多依賴 awk 或 TOML 解析器。
codex_trusts_project() {
    local config="$1" section="[projects.\"$2\"]" inside=0 line
    [ -f "${config}" ] || return 1
    while IFS= read -r line || [ -n "${line}" ]; do
        if [ "${line}" = "${section}" ]; then
            inside=1
        elif [[ "${line}" == "["* ]]; then
            inside=0
        elif [ "${inside}" = 1 ] && [[ "${line}" =~ ^trust_level[[:space:]]*=[[:space:]]*\"trusted\" ]]; then
            return 0
        fi
    done < "${config}"
    return 1
}

# 剩下讀不到狀態的項目, 開案時至少要看到一次。
print_agent_checklist() {
    echo "AI agent（Claude、Codex）還要手動確認的設定，見 docs/extending/agent-hooks.md〈啟用與停用〉："
    echo "  - Claude：第一次開啟專案時確認信任"
    echo "  - Codex：信任專案，並用 /hooks 確認每個 hook"
    echo "  - GitHub：照 docs/workflow.md〈開發流程〉設定 ruleset 與 required checks"
}
