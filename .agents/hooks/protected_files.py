"""防線檔案: hook、agent 設定、CI 與檢查的設定, 用改檔工具改之前要使用者同意 (不分實作前後)。

刪掉一個 CI 步驟或在 `.claude/settings.local.json` 設 `disableAllHooks`, 都不會有檢查變紅。
說明見 docs/extending/agent-hooks.md〈防線檔案〉。
"""

from __future__ import annotations

from pathlib import Path

import approvals

# `.claude/` 包含不進版控的 settings.local.json; `.claude/skills` 是 symlink, 解析後不在這裡。
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
    protected = {path for path in files if is_protected(path)}
    return sorted(protected - approvals.approved(root, "protected"))


def verdict(agent: str, pending: list[str]) -> tuple[str, str]:
    rule = (
        f"{', '.join(pending)} 是防線檔案（hook、agent 設定、CI 或檢查的設定），"
        "改動要先經過使用者同意。"
        "先說明要改什麼、為什麼，會不會讓哪一項檢查變寬鬆。"
    )
    if agent == "codex":
        command = " ".join([*approvals.COMMAND, "protected", *pending])
        return "deny", f"{rule}使用者同意後執行 `{command}`，它會跳確認；確認後再改。"
    return "ask", rule
