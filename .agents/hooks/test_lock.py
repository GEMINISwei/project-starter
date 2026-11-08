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
RULE = "實作已經開始，改測試檔要先經過使用者同意（docs/testing.md〈改程式不改測試〉）。"
EXPLAIN = "先向使用者說明：這個測試驗證的條件、沒過的原因，以及為什麼是測試而不是實作要改。"


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


# 測試放在 apps/*/tests/ 的程式: hook 與 CI 腳本的測試也在 apps/api/tests/。
IMPLEMENTATION_DIRS = ("apps/", "e2e/", ".agents/hooks/", ".github/scripts/", "scripts/")


def is_implementation(path: str) -> bool:
    """改了它就算開始實作: 有測試的程式, 不含測試本身與文件。CI (check-pr-changes.py) 也用它。"""
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
    """分支上改了有測試的程式 (見 is_implementation)。

    只改文件、設定不算: 那些不是測試要鎖住的對象。
    """
    return any(is_implementation(path) for path in changed_files(root))


def approval_file(root: Path, name: str = APPROVAL_NAME) -> Path:
    return (root / (git(root, "rev-parse", "--git-path", name) or "")).resolve()


def approved_paths(root: Path, name: str = APPROVAL_NAME) -> set[str]:
    """只在寫下放行時的 HEAD 上有效: 一有新的 commit, 這次的同意就用完了。"""
    try:
        approval = json.loads(approval_file(root, name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    if approval.get("head") != git(root, "rev-parse", "HEAD"):
        return set()
    return set(approval.get("paths", []))


def pending_test_edits(root: Path, tests: list[str]) -> list[str]:
    """這次要改的測試檔中, 還需要使用者同意的那些 (實作還沒開始就一個都沒有)。"""
    if not tests or not implementation_started(root):
        return []
    return sorted(set(tests) - approved_paths(root))


def verdict(agent: str, pending: list[str]) -> tuple[str, str]:
    """(decision, reason)。Claude 跳確認; Codex 不支援 ask, 擋下並請 agent 用申請指令。"""
    if agent == "codex":
        command = " ".join([*APPROVE_COMMAND, *pending])
        return (
            "deny",
            f"{RULE}{EXPLAIN}說明完執行 `{command}` 申請，它會請使用者確認；"
            "確認後再改一次。不要換其他寫法繞過。",
        )
    return "ask", f"{RULE}{EXPLAIN}"
