"""測試鎖: 哪些是測試檔、實作開始了沒。規則見 docs/testing.md〈改程式不改測試〉。

CI 的 check-pr-changes.py 也用 is_test_file 與 is_implementation, 兩邊的定義才不會分岔。
"""

from __future__ import annotations

from pathlib import Path

import approvals
from approvals import git

RULE = "實作已經開始，改測試檔要先經過使用者同意（docs/testing.md〈改程式不改測試〉）。"
EXPLAIN = "先向使用者說明：這個測試驗證的條件、沒過的原因，以及為什麼是測試而不是實作要改。"
# 測試放在 apps/*/tests/ 的程式: hook 與 CI 腳本的測試也在 apps/api/tests/。
IMPLEMENTATION_DIRS = ("apps/", "e2e/", ".agents/hooks/", ".github/scripts/", "scripts/")


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


def is_implementation(path: str) -> bool:
    """改了它就算開始實作: 有測試的程式, 不含測試本身與文件。"""
    return (
        path.startswith(IMPLEMENTATION_DIRS) and not is_test_file(path) and not path.endswith(".md")
    )


def changed_files(root: Path) -> list[str]:
    """分支相對 origin/main 的差異, 含還沒 commit 與沒追蹤的檔案。"""
    base = git(root, "merge-base", "HEAD", "origin/main") or git(root, "merge-base", "HEAD", "main")
    if not base:
        return []
    changed = (git(root, "diff", "--name-only", base) or "").splitlines()
    changed += (git(root, "ls-files", "--others", "--exclude-standard") or "").splitlines()
    return [path for path in changed if path]


def implementation_started(root: Path) -> bool:
    return any(is_implementation(path) for path in changed_files(root))


def pending_test_edits(root: Path, tests: list[str]) -> list[str]:
    """要改的測試檔中還需要使用者同意的 (實作還沒開始就沒有)。"""
    if not tests or not implementation_started(root):
        return []
    return sorted(set(tests) - approvals.approved(root, "test"))


def verdict(agent: str, pending: list[str]) -> tuple[str, str]:
    """Claude 跳確認; Codex 不支援 ask, 擋下並請 agent 說明後申請。"""
    if agent == "codex":
        command = " ".join([*approvals.COMMAND, "test", *pending])
        return "deny", f"{RULE}{EXPLAIN}使用者同意後執行 `{command}`，它會跳確認；確認後再改。"
    return "ask", f"{RULE}{EXPLAIN}"
