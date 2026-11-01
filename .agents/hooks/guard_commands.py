#!/usr/bin/env python3
"""指令守衛: Claude 與 Codex 的 PreToolUse hook, 擋下這個 repo 明文禁止的指令。

用法 (由 .claude/settings.json 與 .codex/hooks.json 呼叫): guard_commands.py <claude|codex>

兩家的協定相同: stdin 收一個 JSON, 要擋就在 stdout 印 `hookSpecificOutput.permissionDecision`
為 deny 的 JSON, 放行就什麼都不印。參數保留給兩家行為不同的 hook (例如 Codex 不支援 ask),
這支用不到。

只拆解指令的結構 (`&&`、`;`、`|`、子 shell、`bash -c`), 不做完整的 shell 解析: 這是讓 agent
提早停下來的提醒, 不是安全機制, 真正擋得住的是 git 與 CI。只用標準函式庫, 不必先裝相依。
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from collections.abc import Iterator

from test_lock import APPROVAL_NAME, APPROVE_COMMAND

SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")", ";;", "|&"}
WRAPPERS = {"sudo", "env", "command", "exec", "time", "nohup", "xargs"}
SHELLS = {"sh", "bash", "zsh"}
# git 本身的選項中, 後面接一個值的 (`git -C path push`)。
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
PUSH_OPTIONS_WITH_VALUE = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
MAIN_REFS = {"main", "refs/heads/main"}
# `git config` 的 git 2.46 起的子指令, 與舊語法裡會改設定的旗標。
CONFIG_READS = {"get", "list"}
CONFIG_WRITES = {"set", "unset", "rename-section", "remove-section", "edit"}
CONFIG_WRITE_FLAGS = {"--add", "--replace-all", "--unset", "--unset-all", "--edit", "-e"}
PYTHONS = {"python", "python3", "uv", "uvx"}
READ_ONLY = {"cat", "ls", "head", "tail", "less", "stat", "file", "wc", "grep", "rg", "test", "["}
# `<<EOF`、`<<-'EOF'`、`<< "EOF"`; `<<<` 是 here-string, 不算。
HEREDOC = re.compile(r"(?<!<)<<-?(?!<)\s*(['\"]?)(\w+)\1")


def logical_lines(command: str) -> str:
    """去掉 heredoc 的內容, 並把換行當成指令的分隔。

    heredoc 是資料不是指令: commit 訊息裡寫到 `git push origin main` 不該被擋。
    shlex 把換行當空白, 不換成 `;` 的話, 第二行的指令會被當成第一行的參數而漏擋。
    """
    lines: list[str] = []
    delimiters: list[str] = []
    pending = ""
    for line in command.split("\n"):
        if delimiters:
            if line.strip() == delimiters[0]:
                delimiters.pop(0)
            continue
        delimiters += [match.group(2) for match in HEREDOC.finditer(line)]
        if line.endswith("\\"):  # 續行
            pending += line[:-1] + " "
            continue
        lines.append(pending + line)
        pending = ""
    return " ; ".join([*lines, pending])


def simple_commands(command: str) -> Iterator[list[str]]:
    """把整行拆成一個個簡單指令的 argv; `bash -c "…"` 的內容也展開來看。"""
    lexer = shlex.shlex(logical_lines(command), posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError:  # 引號沒閉合: 交給 shell 自己報錯
        return
    current: list[str] = []
    for token in [*tokens, ";"]:
        if token not in SEPARATORS:
            current.append(token)
            continue
        argv = strip_prefixes(current)
        current = []
        if not argv:
            continue
        if argv[0] in SHELLS and "-c" in argv[1:-1]:
            yield from simple_commands(argv[argv.index("-c") + 1])
        else:
            yield argv


def strip_prefixes(argv: list[str]) -> list[str]:
    """去掉開頭的 `FOO=1` 環境變數與 `sudo`、`env` 這類包裝。"""
    index = 0
    while index < len(argv) and ("=" in argv[index].split("/")[0] or argv[index] in WRAPPERS):
        index += 1
    return argv[index:]


def current_branch(cwd: str) -> str:
    result = subprocess.run(
        ["git", "symbolic-ref", "--short", "-q", "HEAD"],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def git_subcommand(argv: list[str]) -> tuple[str, list[str]]:
    index = 1
    while index < len(argv) and argv[index].startswith("-"):
        index += 2 if argv[index] in GIT_OPTIONS_WITH_VALUE else 1
    return (argv[index], argv[index + 1 :]) if index < len(argv) else ("", [])


def pushes_to_main(args: list[str], cwd: str) -> bool:
    positional: list[str] = []
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg in PUSH_OPTIONS_WITH_VALUE:
            skip = True
        elif not arg.startswith("-"):
            positional.append(arg)
    refspecs = positional[1:]
    if not refspecs or refspecs == ["HEAD"]:
        return current_branch(cwd) == "main"
    return any(refspec.lstrip("+").split(":")[-1] in MAIN_REFS for refspec in refspecs)


def self_approval(argv: list[str]) -> bool:
    """測試鎖定的放行只能經過固定寫法的申請指令: 那個寫法才會被兩家要求使用者確認。

    只擋「換寫法執行申請指令」與「寫入放行檔」; `chmod`、`cat` 這類只是提到檔名的不擋。
    """
    if argv[: len(APPROVE_COMMAND)] == APPROVE_COMMAND:
        return False
    program = argv[0].rsplit("/", 1)[-1]
    script = APPROVE_COMMAND[1].rsplit("/", 1)[-1]
    arguments = [arg for arg in argv[1:] if not arg.startswith("-")]
    runs_script = program == script or (
        program in PYTHONS and bool(arguments) and arguments[0].endswith(script)
    )
    touches_approval = any(APPROVAL_NAME in arg for arg in argv)
    writes_approval = touches_approval and (
        program not in READ_ONLY or bool({">", ">>"} & set(argv))
    )
    return runs_script or writes_approval


def skips_hooks(subcommand: str, args: list[str]) -> bool:
    """`--no-verify` 會略過 .githooks/ (commit-msg 檢查 Co-authored-by)。commit 的 `-n` 也是;
    push 的 `-n` 是 --dry-run, 不算。"""
    if "--no-verify" in args:
        return True
    short_flags = [arg for arg in args if arg.startswith("-") and not arg.startswith("--")]
    return subcommand == "commit" and any("n" in flags for flags in short_flags)


def changes_hooks_path(argv: list[str], subcommand: str, args: list[str]) -> bool:
    """`git -c core.hooksPath=…` 與 `git config core.hooksPath …` 都會讓 .githooks/ 失效。"""
    options = argv[1 : len(argv) - len(args) - 1]
    if any(option.lower().startswith("core.hookspath") for option in options):
        return True
    if subcommand != "config" or "core.hookspath" not in [arg.lower() for arg in args]:
        return False
    positional = [arg for arg in args if not arg.startswith("-")]
    action = positional[0] if positional[0] in CONFIG_READS | CONFIG_WRITES else None
    if action in CONFIG_READS:
        return False
    # 設定名之後的就是值; 舊語法只給設定名、沒帶改設定的旗標時是讀取。
    key = [arg.lower() for arg in positional].index("core.hookspath")
    values = positional[key + 1 :]
    writes = action in CONFIG_WRITES or bool(CONFIG_WRITE_FLAGS & set(args)) or bool(values)
    return writes and values != [".githooks"]


def git_violation(argv: list[str], cwd: str) -> str | None:
    subcommand, args = git_subcommand(argv)
    if subcommand == "push" and pushes_to_main(args, cwd):
        return "不可以直接 push 到 main：main 只透過 PR 前進（docs/workflow.md〈開發流程〉）。"
    if subcommand in {"commit", "push", "merge"} and skips_hooks(subcommand, args):
        return (
            "不要略過 git hook（--no-verify）：commit-msg 會檢查 Co-authored-by，"
            "照它的訊息修正後再 commit。"
        )
    if changes_hooks_path(argv, subcommand, args):
        return (
            "不要改 core.hooksPath：.githooks/ 的檢查會整個失效。"
            "它應該是 .githooks（make init dev 會設定）。"
        )
    return None


def violation(argv: list[str], cwd: str) -> str | None:
    if self_approval(argv):
        return (
            f"測試檔的放行只能用 `{' '.join(APPROVE_COMMAND)} <測試檔>` 申請，"
            "它會請使用者確認；不要直接寫放行檔或換寫法呼叫。"
        )
    program = argv[0].rsplit("/", 1)[-1]
    if program == "git":
        return git_violation(argv, cwd)
    if program == "gh" and argv[1:3] == ["pr", "merge"]:
        return "PR 由使用者合併，agent 不自己合併。請回報 CI 結果，等使用者處理。"
    if program == "npm" and {"--force", "--legacy-peer-deps"} & set(argv):
        return (
            "不用 --force／--legacy-peer-deps：遇到 peer 阻擋就停在最新的相容版，"
            "並寫下移除條件（docs/workflow.md〈相依升級〉）。"
        )
    compose = program == "docker-compose" or (
        program == "docker"
        and "compose" in [arg for arg in argv[1:] if not arg.startswith("-")][:2]
    )
    if compose:
        return (
            "不要直接下 docker compose：旗標由 scripts/lib/compose.sh 組（AGENTS.md 硬規則 14），"
            "改用 make start、make services 等指令。"
        )
    return None


def main() -> int:
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "Bash":
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    cwd = payload.get("cwd") or "."
    for argv in simple_commands(command if isinstance(command, str) else shlex.join(command)):
        reason = violation(argv, cwd)
        if reason:
            json.dump(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    }
                },
                sys.stdout,
                ensure_ascii=False,
            )
            return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
