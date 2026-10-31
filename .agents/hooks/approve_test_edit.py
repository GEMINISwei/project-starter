#!/usr/bin/env python3
"""使用者同意後, 放行這次要改的測試檔: python3 .agents/hooks/approve_test_edit.py <測試檔>...

給 Codex 用 (它的 hook 不支援 ask): `.codex/rules/` 讓這個指令一定要使用者確認,
Claude 那邊由 `.claude/settings.json` 的 permissions.ask 做同樣的事。執行的寫法固定,
換寫法呼叫會被 guard_commands.py 擋下, 否則就繞過了確認。

放行只對列出的檔案、只在目前的 HEAD 上有效: 一有新的 commit, 這次的同意就用完了。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from test_lock import approval_file, approved_paths, git, is_test_file, relative, repo_root


def main() -> int:
    cwd = Path.cwd()
    root = repo_root(cwd)
    if root is None or len(sys.argv) < 2:
        print("用法: python3 .agents/hooks/approve_test_edit.py <測試檔>...", file=sys.stderr)
        return 2
    paths = [relative(root, cwd, path) for path in sys.argv[1:]]
    others = [path for path in paths if not is_test_file(path)]
    if others:
        print(f"只能放行測試檔（apps/*/tests/、e2e/tests/）: {others}", file=sys.stderr)
        return 2
    head = git(root, "rev-parse", "HEAD")
    allowed = sorted(approved_paths(root) | set(paths))
    approval_file(root).write_text(json.dumps({"head": head, "paths": allowed}), encoding="utf-8")
    print(f"已放行（下一個 commit 之前有效）: {', '.join(paths)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
