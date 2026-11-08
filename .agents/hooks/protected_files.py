"""防線檔案: hook、agent 設定、CI 與檢查的設定, 改動前要使用者同意。

改檔 hook (guard_tests.py) 與指令守衛 (guard_commands.py) 都用它。這些檔案決定了其他規則擋不擋得住:
刪掉一個 CI 步驟, required check 的名字還在, 照樣顯示綠燈; 在 `.claude/settings.local.json` 設
`disableAllHooks`, 所有 hook 就安靜地不生效。說明見 docs/extending/agent-hooks.md〈防線檔案〉。

跟測試鎖不同, 不分實作前後。放行的格式與期限沿用測試鎖 (只對列出的檔案、只在目前的 HEAD 有效)。
"""

from __future__ import annotations

from pathlib import Path

from test_lock import approved_paths

APPROVAL_NAME = "agent-approved-protected-edits"
APPROVE_COMMAND = ["python3", ".agents/hooks/approve_protected_edit.py"]

# 底下的任何檔案都算。`.claude/` 包含不進版控的 settings.local.json;
# `.claude/skills` 是指向 `.agents/skills` 的 symlink, 路徑解析後不在這裡。
PROTECTED_DIRS = (
    ".agents/hooks/",
    ".claude/",
    ".codex/",
    ".githooks/",
    ".github/workflows/",
    ".github/scripts/",
)
# lint、型別、架構邊界、未使用匯出與覆蓋率門檻的設定, 以及 `make check` 的入口。
PROTECTED_FILES = (
    "apps/api/pyproject.toml",
    "apps/web/package.json",
    "apps/web/eslint.config.mjs",
    "apps/web/.dependency-cruiser.cjs",
    "apps/web/knip.ts",
    "apps/web/tsconfig.json",
    "apps/web/vitest.config.ts",
    "scripts/check.sh",
    "Makefile",
)


def is_protected(path: str) -> bool:
    return path.startswith(PROTECTED_DIRS) or path in PROTECTED_FILES


def pending_protected_edits(root: Path, files: list[str]) -> list[str]:
    """這次要改的防線檔案中, 還需要使用者同意的那些。"""
    protected = {path for path in files if is_protected(path)}
    return sorted(protected - approved_paths(root, APPROVAL_NAME))


def verdict(agent: str, pending: list[str]) -> tuple[str, str]:
    """(decision, reason)。Claude 跳確認; Codex 不支援 ask, 擋下並請 agent 用申請指令。"""
    rule = (
        f"{', '.join(pending)} 是防線本身的檔案（hook、agent 設定、CI 或檢查的設定），"
        "改動要先經過使用者同意（docs/extending/agent-hooks.md〈防線檔案〉）。"
        "先向使用者說明要改什麼、為什麼，以及會不會讓哪一項檢查變寬鬆。"
    )
    if agent == "codex":
        command = " ".join([*APPROVE_COMMAND, *pending])
        return "deny", f"{rule}說明完執行 `{command}` 申請，它會請使用者確認；確認後再改一次。"
    return "ask", rule
