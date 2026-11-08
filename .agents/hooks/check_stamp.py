#!/usr/bin/env python3
"""make check 全部通過時的工作目錄指紋: python3 .agents/hooks/check_stamp.py record

scripts/check.sh 在不帶參數的 make check 全部通過後呼叫 record; Stop hook (require_check.py)
比對現在的指紋, 沒變就代表這個狀態已經檢查過。

指紋是工作目錄實際內容 (含還沒 commit 與沒追蹤的檔案) 的 git tree, 不含 Markdown, 也不看 HEAD:
agent 的習慣是跑完檢查再 commit, commit 與只改文件不該讓它重跑幾分鐘的 make check;
程式改了任何一個字就要重跑。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from test_lock import git, repo_root

# 放在 .git/ 裡: 不會被 commit, 只對這個 checkout 有效。
STAMP_NAME = "agent-last-check"


def stamp_file(root: Path) -> Path:
    return (root / (git(root, "rev-parse", "--git-path", STAMP_NAME) or "")).resolve()


def fingerprint(root: Path) -> str:
    """用暫時的 index 把工作目錄寫成 tree, 不動到真正的 index (使用者 stage 的內容不受影響)。"""
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(tmp) / "index")}
        for args in (
            ["add", "-A", "--", "."],
            ["rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", "*.md"],
        ):
            subprocess.run(  # noqa: S603
                ["git", *args],  # noqa: S607
                cwd=root,
                env=env,
                capture_output=True,
                check=True,
            )
        result = subprocess.run(
            ["git", "write-tree"],  # noqa: S607
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
    return result.stdout.strip()


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
