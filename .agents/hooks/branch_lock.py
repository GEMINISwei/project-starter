"""一次一個 PR 的共用判斷: 使用者有沒有開著的 PR、使用者放行了哪些分支。

guard_commands.py 與 approve_parallel_branch.py 都用它。規則見 docs/workflow.md〈一次一個 PR〉。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from test_lock import git

# 放在 .git/ 裡: 不會被 commit, 只對這個 checkout 有效。
APPROVAL_NAME = "agent-approved-parallel-branches"
APPROVE_COMMAND = ["python3", ".agents/hooks/approve_parallel_branch.py"]
# 只算使用者自己開的: Dependabot 開的安全更新不是 agent 進行中的工作。
GH_OPEN_PRS = ("gh", "pr", "list", "--author", "@me", "--state", "open", "--json", "headRefName")


def approval_file(root: Path) -> Path:
    return (root / (git(root, "rev-parse", "--git-path", APPROVAL_NAME) or "")).resolve()


def approved_branches(root: Path) -> set[str]:
    """放行針對分支名稱: 插隊的那一個分支開分支、開 PR 都不再問。"""
    try:
        branches = json.loads(approval_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {branch for branch in branches if isinstance(branch, str)}


def open_prs(cwd: str) -> list[str]:
    """使用者開著的 PR 的分支名稱。查不到 (沒網路、沒登入) 時當作沒有: 這是流程規則,
    不是部署那種安全邊界, 沒網路時擋開分支只會礙事, 而且本來也開不了 PR。"""
    try:
        result = subprocess.run(  # noqa: S603
            [*GH_OPEN_PRS],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        prs = json.loads(result.stdout) if result.returncode == 0 else []
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return []
    return [str(pr.get("headRefName", "")) for pr in prs if isinstance(pr, dict)]
