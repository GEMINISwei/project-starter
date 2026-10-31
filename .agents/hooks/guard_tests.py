#!/usr/bin/env python3
"""測試鎖定: Claude 與 Codex 的 PreToolUse hook, 開始實作之後改測試檔要使用者同意。

用法 (由 .claude/settings.json 與 .codex/hooks.json 呼叫): guard_tests.py <claude|codex>

兩家在這裡行為不同, 所以才需要參數:
- Claude 回 ask, 畫面直接跳出確認, 使用者同意就繼續。
- Codex 的 PreToolUse 不支援 ask, 只能 deny; 理由裡請 agent 說明後執行 approve_test_edit.py 申請,
  `.codex/rules/` 讓那個指令一定要使用者確認, 確認後再改就會放行。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from test_lock import (
    APPROVAL_NAME,
    APPROVE_COMMAND,
    approved_paths,
    implementation_started,
    is_test_file,
    relative,
    repo_root,
)

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
# Codex 的 apply_patch 把整段 patch 放在 command 裡, 檔名在這幾種標頭行。
PATCH_FILE = re.compile(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$", re.M)
RULE = "實作已經開始，改測試檔要先經過使用者同意（docs/testing.md〈改程式不改測試〉）。"
EXPLAIN = "先向使用者說明：這個測試驗證的條件、沒過的原因，以及為什麼是測試而不是實作要改。"


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
    if any(APPROVAL_NAME in path for path in files):
        respond("deny", "放行檔只能由使用者確認過的申請指令寫入，不要直接修改。")
        return 0
    tests = [path for path in files if is_test_file(path)]
    if not tests or not implementation_started(root):
        return 0
    pending = sorted(set(tests) - approved_paths(root))
    if not pending:
        return 0
    if agent == "codex":
        command = " ".join([*APPROVE_COMMAND, *pending])
        respond(
            "deny",
            f"{RULE}{EXPLAIN}說明完執行 `{command}` 申請，它會請使用者確認；"
            "確認後再改一次。不要換其他寫法繞過。",
        )
    else:
        respond("ask", f"{RULE}{EXPLAIN}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
