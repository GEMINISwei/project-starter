#!/usr/bin/env python3
"""改檔 hook: Claude 與 Codex 的 PreToolUse hook, 這兩種檔案改動前要使用者同意。

- 測試檔: 開始實作之後 (test_lock.py)
- 防線檔案 (hook、agent 設定、CI、檢查的設定): 任何時候 (protected_files.py)

用法 (由 .claude/settings.json 與 .codex/hooks.json 呼叫): guard_tests.py <claude|codex>

兩家在這裡行為不同, 所以才需要參數:
- Claude 回 ask, 畫面直接跳出確認, 使用者同意就繼續。
- Codex 的 PreToolUse 不支援 ask, 只能 deny; 理由裡請 agent 說明後執行對應的申請指令
  (approve_test_edit.py、approve_protected_edit.py), `.codex/rules/` 讓它一定要使用者確認,
  確認後再改就會放行。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import branch_lock
import protected_files
import test_lock
from test_lock import is_test_file, pending_test_edits, relative, repo_root, verdict

# agent 不能直接寫的放行檔: 只能由使用者確認過的申請指令寫入。
APPROVAL_NAMES = (
    test_lock.APPROVAL_NAME,
    branch_lock.APPROVAL_NAME,
    protected_files.APPROVAL_NAME,
)

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
# Codex 的 apply_patch 把整段 patch 放在 command 裡, 檔名在這幾種標頭行。
PATCH_FILE = re.compile(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$", re.M)


def edited_paths(payload: dict[str, object]) -> list[str]:
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    if tool in EDIT_TOOLS:
        path = tool_input.get("file_path") or tool_input.get("notebook_path")
        return [path] if isinstance(path, str) else []
    if tool == "apply_patch" and isinstance(tool_input.get("command"), str):
        return [name.strip() for name in PATCH_FILE.findall(tool_input["command"])]
    return []


def respond(decision: str, reason: str) -> None:
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }
    json.dump(output, sys.stdout, ensure_ascii=False)


def main() -> int:
    agent = sys.argv[1] if len(sys.argv) > 1 else "claude"
    payload = json.load(sys.stdin)
    cwd = Path(payload.get("cwd") or ".")
    root = repo_root(cwd)
    paths = edited_paths(payload)
    if root is None or not paths:
        return 0
    files = [relative(root, cwd, path) for path in paths]
    if any(name in path for path in files for name in APPROVAL_NAMES):
        respond("deny", "放行檔只能由使用者確認過的申請指令寫入，不要直接修改。")
        return 0
    protected = protected_files.pending_protected_edits(root, files)
    if protected:
        respond(*protected_files.verdict(agent, protected))
        return 0
    pending = pending_test_edits(root, [path for path in files if is_test_file(path)])
    if pending:
        respond(*verdict(agent, pending))
    return 0


if __name__ == "__main__":
    sys.exit(main())
