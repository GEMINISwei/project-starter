#!/usr/bin/env python3
"""指令守衛: Claude 與 Codex 的 PreToolUse hook, 擋下這個 repo 明文禁止的指令。

用法 (由 .claude/settings.json 與 .codex/hooks.json 呼叫): guard_commands.py <claude|codex>

兩家的協定相同: stdin 收一個 JSON, 要擋就在 stdout 印 `hookSpecificOutput.permissionDecision`
為 deny 的 JSON, 放行就什麼都不印。參數保留給兩家行為不同的 hook (例如 Codex 不支援 ask),
這支用不到。

只拆解指令的結構 (`&&`、`;`、`|`、子 shell、`bash -c`), 不做完整的 shell 解析: 這是讓 agent
提早停下來的提醒, 不是安全機制, 真正擋得住的是 git 與 CI。只用標準函式庫, 不必先裝相依。
"""

import json
import shlex
import subprocess
import sys
from collections.abc import Iterator

SEPARATORS = {"&&", "||", ";", "|", "&", "(", ")", ";;", "|&"}
WRAPPERS = {"sudo", "env", "command", "exec", "time", "nohup", "xargs"}
SHELLS = {"sh", "bash", "zsh"}
# git 本身的選項中, 後面接一個值的 (`git -C path push`)。
GIT_OPTIONS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
PUSH_OPTIONS_WITH_VALUE = {"-o", "--push-option", "--repo", "--receive-pack", "--exec"}
MAIN_REFS = {"main", "refs/heads/main"}


def simple_commands(command: str) -> Iterator[list[str]]:
    """把整行拆成一個個簡單指令的 argv; `bash -c "…"` 的內容也展開來看。"""
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
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


def violation(argv: list[str], cwd: str) -> str | None:
    program = argv[0].rsplit("/", 1)[-1]
    if program == "git":
        subcommand, args = git_subcommand(argv)
        if subcommand == "push" and pushes_to_main(args, cwd):
            return "不可以直接 push 到 main：main 只透過 PR 前進（docs/workflow.md〈開發流程〉）。"
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
