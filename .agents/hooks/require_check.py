#!/usr/bin/env python3
"""Stop hook: agent 收尾前, 改過的程式要跑過 make check。

用法 (由 .claude/settings.json 與 .codex/hooks.json 呼叫): require_check.py <claude|codex>

兩家的 Stop 格式相同: 回 `{"decision": "block", "reason": …}` 時 agent 會繼續做,
reason 就是它收到的提示。
沒有理由攔就什麼都不印。agent 參數兩家行為一樣, 留著是為了跟其他 hook 用同一種呼叫寫法。

不攔的情況:
- 同一輪已經被攔過一次 (stop_hook_active): agent 停下來可能只是要問使用者問題, 說明一句就能結束,
  不會被逼著先跑幾分鐘的 make check, 也不會無限迴圈。
- 分支上沒有改動, 或只改了 Markdown。
- 工作目錄跟上次 make check 全部通過時一樣 (check_stamp.py)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from check_stamp import checked
from test_lock import changed_files, repo_root

REASON = (
    "程式改過，還沒跑過 `make check`（或通過之後又改了）。回報使用者之前先跑 `make check`，"
    "全綠再收尾；紅了就修好再跑（AGENTS.md〈改完之後〉）。"
    "如果這次停下來是要問使用者問題、等使用者回覆，而不是回報做完，說明一句就可以結束。"
)


def main() -> int:
    payload = json.load(sys.stdin)
    if payload.get("stop_hook_active"):
        return 0
    root = repo_root(Path(payload.get("cwd") or "."))
    if root is None:
        return 0
    code = [path for path in changed_files(root) if not path.endswith(".md")]
    if not code or checked(root):
        return 0
    json.dump({"decision": "block", "reason": REASON}, sys.stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
