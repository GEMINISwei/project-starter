#!/usr/bin/env python3
"""PR 的改動檢查: BASE_SHA=… HEAD_SHA=… PR_BODY=… .github/scripts/check-pr-changes.py

pr.yml 呼叫, 本機也能跑。agent 這一側的 hook 換個寫法就可能繞過, 這裡在 CI 上再檢查一次:

1. 實作開始之後還改到測試檔: PR 描述要寫出那個檔案的路徑, 說明為什麼改
   (docs/testing.md〈改程式不改測試〉)。合併 main 帶進來的 commit 不算。
2. 動到防線檔案或 agent 的說明: 「檢查」段要列出那個檔案或它的目錄, 審查時才一定會被看到
   (docs/extending/agent-hooks.md〈防線檔案〉)。
3. 新增的抑制註解: 同一行要寫理由 (docs/development.md〈抑制註解〉)。只看這個 PR 新增的行。

測試檔與防線檔案的定義直接讀 .agents/hooks/, 不另抄一份。要能在 Python 3.9 上跑 (macOS 內建)。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# 這兩個模組在 .agents/hooks/, 要先加進 sys.path 才匯入得到。
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / ".agents" / "hooks"))

from protected_files import is_protected
from test_lock import is_implementation, is_test_file

# agent 的說明: 不執行檢查, 所以 hook 不攔, 但改了會改變 agent 的行為, 審查時要看到。
AGENT_INSTRUCTIONS = ("AGENTS.md", ".agents/skills/")
CODE_SUFFIXES = (".py", ".ts", ".tsx", ".js", ".mjs", ".cjs")
# 呼叫子行程的警告: hook 與測試用固定參數呼叫 git、gh 是常態, 每次寫理由只是噪音。
EXEMPT_NOQA = {"S603", "S607"}

NOQA = re.compile(r"#\s*noqa(?::\s*(?P<codes>[A-Z0-9]+(?:\s*,\s*[A-Z0-9]+)*))?(?P<rest>.*)$")
TYPE_IGNORE = re.compile(r"#\s*type:\s*ignore(?:\[[^\]]*\])?(?P<rest>.*)$")
ESLINT = re.compile(r"(?://|/\*)\s*eslint-disable[\w-]*(?P<rest>.*)$")
TS_DIRECTIVE = re.compile(r"//\s*@ts-(?:expect-error|ignore)(?P<rest>.*)$")
PYTEST_SKIP = re.compile(r"pytest\.(?:mark\.skip(?:if)?|skip)\b(?P<rest>.*)$")
JS_SKIP = re.compile(r"\b(?:it|test|describe)\.skip\((?P<rest>.*)$")


def git(*args: str) -> str:
    return subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def sections(body: str) -> dict[str, str]:
    """`## 標題` 底下的內容, 去掉 HTML 註解。"""
    body = re.sub(r"<!--.*?-->", "", body.replace("\r", ""), flags=re.DOTALL)
    result: dict[str, str] = {}
    current = ""
    for line in body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip()
            result.setdefault(current, "")
        elif current:
            result[current] += line + "\n"
    return result


def tests_changed_after_implementation(base: str, head: str) -> list[str]:
    """從第一個開始實作的 commit 起 (含那一個), 之後改到的測試檔。

    「開始實作」跟 hook 的測試鎖用同一個判斷 (test_lock.is_implementation)。
    """
    started = False
    changed: set[str] = set()
    for commit in git("rev-list", "--reverse", "--no-merges", f"{base}..{head}").split():
        files = git("diff-tree", "--no-commit-id", "--name-only", "-r", commit).splitlines()
        started = started or any(is_implementation(path) for path in files)
        if started:
            changed.update(path for path in files if is_test_file(path))
    return sorted(changed)


def is_guarded(path: str) -> bool:
    return is_protected(path) or path.startswith(AGENT_INSTRUCTIONS)


def listed(path: str, text: str) -> bool:
    """檔案本身或它的任何一層目錄 (結尾帶 `/`) 出現在 text 裡。"""
    parts = path.split("/")
    candidates = [path] + ["/".join(parts[:index]) + "/" for index in range(1, len(parts))]
    return any(candidate in text for candidate in candidates)


def added_lines(base: str, head: str) -> list[tuple[str, str]]:
    """(檔案, 新增的那一行), 只看程式碼。"""
    diff = git("diff", "-U0", "--no-color", f"{base}...{head}")
    result = []
    path = ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else ""
        elif line.startswith("+") and path.endswith(CODE_SUFFIXES):
            result.append((path, line[1:]))
    return result


def has_comment(rest: str, marker: str) -> bool:
    """rest 裡在 marker 之後還有文字 (marker 為空時, rest 本身有文字)。"""
    if not marker:
        return bool(rest.strip(" */"))
    _, found, reason = rest.partition(marker)
    return bool(found) and bool(reason.strip(" */"))


def missing_reason(line: str) -> str | None:
    """這一行的抑制註解沒寫理由時, 回傳它是哪一種。"""
    match = NOQA.search(line)
    if match:
        codes = {code.strip() for code in (match.group("codes") or "").split(",") if code.strip()}
        if codes and codes <= EXEMPT_NOQA:
            return None
        return None if has_comment(match.group("rest"), "#") else "noqa"
    match = TYPE_IGNORE.search(line)
    if match:
        return None if has_comment(match.group("rest"), "#") else "type: ignore"
    match = ESLINT.search(line)
    if match:
        return None if has_comment(match.group("rest"), "--") else "eslint-disable（用 `-- 理由`）"
    match = TS_DIRECTIVE.search(line)
    if match:
        return None if has_comment(match.group("rest"), "") else "@ts-expect-error"
    match = PYTEST_SKIP.search(line)
    if match:
        rest = match.group("rest")
        has_reason = "reason=" in rest or re.match(r"\(\s*['\"]", rest) is not None
        return None if has_reason else "pytest skip（要帶 reason）"
    match = JS_SKIP.search(line)
    if match:
        return None if has_comment(match.group("rest"), "//") else "skip（同一行用 `//` 寫理由）"
    return None


def current_body() -> str:
    """PR 目前的描述。事件帶的 PR_BODY 是觸發當下的內容: push 與改描述幾乎同時發生時,
    pr.yml 的 cancel-in-progress 可能留下帶著舊描述的那一次, 所以先用 gh 讀現在的。"""
    number = os.environ.get("PR_NUMBER", "")
    if number:
        try:
            result = subprocess.run(  # noqa: S603
                ["gh", "pr", "view", number, "--json", "body", "--jq", ".body"],  # noqa: S607
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout
        except (OSError, subprocess.TimeoutExpired):
            pass
    return os.environ.get("PR_BODY", "")


def main() -> int:
    base = os.environ["BASE_SHA"]
    head = os.environ["HEAD_SHA"]
    body = current_body()
    checks = sections(body).get("檢查", "")
    errors = []

    for path in tests_changed_after_implementation(base, head):
        if path not in body:
            errors.append(
                f"{path}: 實作開始之後改了這個測試檔，PR 描述要寫出它的路徑並說明為什麼改"
                "（原本的斷言哪裡錯）"
            )

    changed = git("diff", "--name-only", f"{base}...{head}").splitlines()
    for path in sorted(path for path in changed if is_guarded(path)):
        if not listed(path, checks):
            errors.append(
                f"{path}: 這是防線檔案或 agent 的說明，「檢查」段要列出它（或它的目錄），"
                "說明改了什麼、會不會讓哪一項檢查變寬鬆"
            )

    for path, line in added_lines(base, head):
        kind = missing_reason(line)
        if kind:
            errors.append(f"{path}: 新增的 {kind} 要在同一行寫理由：{line.strip()}")

    for error in errors:
        print(error, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
