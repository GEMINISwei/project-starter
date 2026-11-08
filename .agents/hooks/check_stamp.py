#!/usr/bin/env python3
"""make check 全部通過時的工作目錄指紋: python3 .agents/hooks/check_stamp.py record

scripts/check.sh 在不帶參數的 make check 全部通過後呼叫 record; Stop hook (require_check.py)
比對現在的指紋, 沒變就代表這個狀態已經檢查過。指紋涵蓋 HEAD、還沒 commit 的差異與沒追蹤的檔案內容,
所以 commit 之後不必重跑, 但任何一個字改了都要重跑。
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

from test_lock import git, repo_root

# 放在 .git/ 裡: 不會被 commit, 只對這個 checkout 有效。
STAMP_NAME = "agent-last-check"


def stamp_file(root: Path) -> Path:
    return (root / (git(root, "rev-parse", "--git-path", STAMP_NAME) or "")).resolve()


def fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    digest.update((git(root, "rev-parse", "HEAD") or "").encode())
    digest.update((git(root, "diff", "HEAD", "--binary") or "").encode())
    untracked = sorted((git(root, "ls-files", "--others", "--exclude-standard") or "").splitlines())
    for path in untracked:
        digest.update(path.encode())
        digest.update((git(root, "hash-object", "--", path) or "").encode())
    return digest.hexdigest()


def checked(root: Path) -> bool:
    """現在的工作目錄跟上次 make check 全部通過時一樣。"""
    try:
        return stamp_file(root).read_text(encoding="utf-8").strip() == fingerprint(root)
    except OSError:
        return False


def main() -> int:
    root = repo_root(Path.cwd())
    if root is None or sys.argv[1:] != ["record"]:
        print("用法: python3 .agents/hooks/check_stamp.py record", file=sys.stderr)
        return 2
    stamp_file(root).write_text(fingerprint(root), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
