#!/usr/bin/env python3
"""使用者同意插隊後, 放行這個分支: python3 .agents/hooks/approve_parallel_branch.py <分支>...

有開著的 PR 時開新分支要使用者同意 (docs/workflow.md〈一次一個 PR〉)。Claude 由 hook 直接跳確認,
Codex 的 hook 不支援 ask, 由 agent 執行這個指令申請, `.codex/rules/` 讓它一定要使用者確認;
Claude 那邊由 `.claude/settings.json` 的 permissions.ask 做同樣的事。執行的寫法固定,
換寫法呼叫會被 guard_commands.py 擋下, 否則就繞過了確認。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from branch_lock import approval_file, approved_branches
from test_lock import git, repo_root


def main() -> int:
    root = repo_root(Path.cwd())
    if root is None or len(sys.argv) < 2:
        print("用法: python3 .agents/hooks/approve_parallel_branch.py <分支>...", file=sys.stderr)
        return 2
    branches = sys.argv[1:]
    invalid = [name for name in branches if git(root, "check-ref-format", "--branch", name) is None]
    if invalid:
        print(f"不是合法的分支名稱: {invalid}", file=sys.stderr)
        return 2
    allowed = sorted(approved_branches(root) | set(branches))
    approval_file(root).write_text(json.dumps(allowed), encoding="utf-8")
    print(f"已放行: {', '.join(branches)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
