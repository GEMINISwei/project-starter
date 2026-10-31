"""測試鎖定的共用判斷: 哪些是測試檔、實作開始了沒、使用者放行了哪些檔案。

guard_tests.py 與 approve_test_edit.py 都用它, 兩邊對「測試檔」的定義才不會分岔。
規則本身見 docs/testing.md〈改程式不改測試〉。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

# 放在 .git/ 裡: 不會被 commit, 換一台機器或重新 clone 就沒了, 本來就只對這一次有效。
APPROVAL_NAME = "agent-approved-test-edits"
APPROVE_COMMAND = ["python3", ".agents/hooks/approve_test_edit.py"]


def git(cwd: Path, *args: str) -> str | None:
    result = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def repo_root(cwd: Path) -> Path | None:
    root = git(cwd, "rev-parse", "--show-toplevel")
    return Path(root).resolve() if root else None


def relative(root: Path, cwd: Path, path: str) -> str:
    absolute = (cwd / path).resolve()
    try:
        return absolute.relative_to(root).as_posix()
    except ValueError:  # repo 以外的檔案
        return absolute.as_posix()


def is_test_file(path: str) -> bool:
    """各 app 的 `tests/` 與 `e2e/tests/`, 輔助檔與測試資料也算。"""
    parts = path.split("/")
    in_app_tests = len(parts) > 3 and parts[0] == "apps" and parts[2] == "tests"
    return in_app_tests or path.startswith("e2e/tests/")


def implementation_started(root: Path) -> bool:
    """分支相對 origin/main 的差異 (含還沒 commit 與沒追蹤的) 有 apps/、e2e/ 底下的非測試檔案。

    只改文件、設定不算: 那些不是測試要鎖住的對象。
    """
    base = git(root, "merge-base", "HEAD", "origin/main") or git(root, "merge-base", "HEAD", "main")
    if not base:
        return False
    changed = (git(root, "diff", "--name-only", base) or "").splitlines()
    changed += (git(root, "ls-files", "--others", "--exclude-standard") or "").splitlines()
    return any(
        path.startswith(("apps/", "e2e/")) and not is_test_file(path) for path in changed if path
    )


def approval_file(root: Path) -> Path:
    return (root / (git(root, "rev-parse", "--git-path", APPROVAL_NAME) or "")).resolve()


def approved_paths(root: Path) -> set[str]:
    """只在寫下放行時的 HEAD 上有效: 一有新的 commit, 這次的同意就用完了。"""
    try:
        approval = json.loads(approval_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    if approval.get("head") != git(root, "rev-parse", "HEAD"):
        return set()
    return set(approval.get("paths", []))
