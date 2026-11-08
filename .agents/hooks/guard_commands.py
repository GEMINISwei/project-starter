#!/usr/bin/env python3
"""指令守衛: Claude 與 Codex 的 PreToolUse hook, 擋下這個 repo 明文禁止的指令。

用法 (由 .claude/settings.json 與 .codex/hooks.json 呼叫): guard_commands.py <claude|codex>

兩家的協定相同: stdin 收一個 JSON, 要擋就在 stdout 印 `hookSpecificOutput.permissionDecision`
為 deny 的 JSON, 放行就什麼都不印。參數給兩家行為不同的地方: 發布 release 與用 shell 改測試檔時
Claude 回 ask, Codex 不支援 ask, 改由 .codex/rules/ 或申請指令要求確認。

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
from pathlib import Path

import branch_lock
import protected_files
import test_lock
from test_lock import (
    is_test_file,
    pending_test_edits,
    relative,
    repo_root,
    verdict,
)

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
# 發布 release 會直接部署: agent 只能經過這個固定寫法, 兩家的設定讓它一定跳確認。
PUBLISH_COMMAND = ".agents/skills/release/scripts/publish.sh"
# 會觸發部署或改掉已發布版本的 gh 指令。
DEPLOYING_RELEASE = {"create", "edit", "delete"}
# 合併、轉 Ready 與發 release 的 GraphQL mutation: 換成 API 呼叫一樣不能由 agent 做。
FORBIDDEN_MUTATIONS = (
    "mergePullRequest",
    "markPullRequestReadyForReview",
    "enablePullRequestAutoMerge",
    "createRelease",
    "updateRelease",
    "deleteRelease",
)
# `gh api` 後面接一個值的選項; 帶了欄位而沒指定方法時, gh 會改用 POST。
GH_API_OPTIONS_WITH_VALUE = {
    "-X",
    "--method",
    "-f",
    "--raw-field",
    "-F",
    "--field",
    "-H",
    "--header",
    "--input",
    "-q",
    "--jq",
    "-t",
    "--template",
    "--hostname",
    "--cache",
    "-p",
    "--preview",
}
GH_API_FIELDS = {"-f", "--raw-field", "-F", "--field", "--input"}
# 會合併 PR、動到 release、觸發或重跑 workflow 的 REST 端點。
DEPLOYING_ENDPOINT = re.compile(
    r"/pulls/\d+/merge$|/releases(/|$)|/dispatches$|/actions/runs/\d+/rerun"
)
# deploy.yml 的 `name:`; 重跑它的 run 等於重新部署。
DEPLOY_WORKFLOW = "Deploy"
# 輸出重新導向; 目標是下一個 token。
REDIRECTS = {">", ">>", ">|", "&>", "&>>"}
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


# 需要使用者確認的放行: (放行檔名, 固定寫法的申請指令, 申請的對象)。
APPROVALS = (
    (test_lock.APPROVAL_NAME, test_lock.APPROVE_COMMAND, "<測試檔>"),
    (branch_lock.APPROVAL_NAME, branch_lock.APPROVE_COMMAND, "<分支>"),
    (protected_files.APPROVAL_NAME, protected_files.APPROVE_COMMAND, "<檔案>"),
)


def self_approval(argv: list[str]) -> str | None:
    """放行只能經過固定寫法的申請指令: 那個寫法才會被兩家要求使用者確認。回傳該用的寫法。

    只擋「換寫法執行申請指令」與「寫入放行檔」; `chmod`、`cat` 這類只是提到檔名的不擋。
    """
    for approval_name, approve_command, target in APPROVALS:
        if argv[: len(approve_command)] == approve_command:
            continue
        program = argv[0].rsplit("/", 1)[-1]
        script = approve_command[1].rsplit("/", 1)[-1]
        arguments = [arg for arg in argv[1:] if not arg.startswith("-")]
        runs_script = program == script or (
            program in PYTHONS and bool(arguments) and arguments[0].endswith(script)
        )
        touches_approval = any(approval_name in arg for arg in argv)
        writes_approval = touches_approval and (
            program not in READ_ONLY or bool({">", ">>"} & set(argv))
        )
        if runs_script or writes_approval:
            return f"{' '.join(approve_command)} {target}"
    return None


def bypasses_publish(argv: list[str]) -> bool:
    """換寫法執行 publish.sh (`bash …`、`./…`、從別的目錄) 不會被要求確認。"""
    if argv[0] == PUBLISH_COMMAND:
        return False
    script = PUBLISH_COMMAND.rsplit("/", 1)[-1]
    program = argv[0].rsplit("/", 1)[-1]
    arguments = [arg for arg in argv[1:] if not arg.startswith("-")]
    return program == script or (
        program in SHELLS and bool(arguments) and arguments[0].endswith(script)
    )


def deploys(argv: list[str]) -> bool:
    """`gh release create/edit/delete` 與手動觸發 Deploy workflow。"""
    if argv[1:2] == ["release"]:
        return bool(argv[2:3]) and argv[2] in DEPLOYING_RELEASE
    return argv[1:3] == ["workflow", "run"] and any(
        arg.lower().startswith("deploy") for arg in argv[3:]
    )


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


def gh_api_request(argv: list[str]) -> tuple[str, str, list[str]]:
    """(方法, 端點, 其餘參數)。沒指定方法時照 gh 的規則: 有欄位就是 POST。"""
    method = ""
    endpoint = ""
    has_fields = False
    index = 2
    while index < len(argv):
        arg = argv[index]
        name = arg.split("=", 1)[0]
        if name in GH_API_OPTIONS_WITH_VALUE:
            value = arg.split("=", 1)[1] if "=" in arg else (argv[index + 1 : index + 2] or [""])[0]
            if name in {"-X", "--method"}:
                method = value.upper()
            has_fields = has_fields or name in GH_API_FIELDS
            index += 1 if "=" in arg else 2
            continue
        if not arg.startswith("-") and not endpoint:
            endpoint = arg
        index += 1
    return method or ("POST" if has_fields else "GET"), endpoint, argv


def gh_violation(argv: list[str], cwd: str) -> str | None:
    if argv[1:3] == ["pr", "merge"]:
        return "PR 由使用者合併，agent 不自己合併。請回報 CI 結果，等使用者處理。"
    if argv[1:3] == ["pr", "ready"] and "--undo" not in argv:
        return "Ready for review 由使用者決定，agent 不自己轉。請回報 PR 的狀態，等使用者處理。"
    if argv[1:2] == ["api"]:
        method, endpoint, args = gh_api_request(argv)
        if endpoint == "graphql":
            if any(name in arg for arg in args for name in FORBIDDEN_MUTATIONS):
                return (
                    "合併、轉 Ready 與發 release 由使用者做，換成 GraphQL 也一樣。"
                    "請回報狀態，等使用者處理。"
                )
        elif method != "GET" and DEPLOYING_ENDPOINT.search(endpoint.split("?")[0]):
            return (
                "這個 API 會合併 PR、動到 release 或觸發／重跑 workflow，可能直接部署，"
                "agent 不能用 API 繞過。合併由使用者做；發版走 release skill 的 publish.sh；"
                "要重跑 CI 用 `gh run rerun <id>`。"
            )
    if argv[1:3] == ["run", "rerun"]:
        return rerun_violation(argv, cwd)
    return None


def rerun_violation(argv: list[str], cwd: str) -> str | None:
    """重跑 Deploy 的 run 等於重新部署; 指令本身看不出 workflow, 要問 gh。"""
    run_ids = [arg for arg in argv[3:] if not arg.startswith("-")]
    workflow = None
    if run_ids:
        try:
            result = subprocess.run(  # noqa: S603
                ["gh", "run", "view", run_ids[0], "--json", "workflowName"],  # noqa: S607
                cwd=cwd,
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            if result.returncode == 0:
                workflow = json.loads(result.stdout).get("workflowName")
        except (OSError, ValueError, subprocess.TimeoutExpired):
            workflow = None
    if workflow is None:
        return (
            "無法確認這個 run 屬於哪個 workflow（要指定 run id，而且 gh 要查得到）。"
            "重跑 Deploy 等於重新部署，所以先擋下；請使用者確認後由使用者自己重跑。"
        )
    if workflow == DEPLOY_WORKFLOW:
        return "重跑 Deploy 等於重新部署，由使用者自己觸發（docs/operations.md〈自動部署〉）。"
    return None


def written_paths(argv: list[str]) -> list[str]:
    """這個指令會寫入、刪除或還原的檔案路徑。只認明確指名檔案的常見寫法。"""
    paths = [argv[index + 1] for index, arg in enumerate(argv[:-1]) if arg in REDIRECTS]
    program = argv[0].rsplit("/", 1)[-1]
    args = [arg for arg in argv[1:] if arg not in REDIRECTS]
    positional = [arg for arg in args if not arg.startswith("-")]
    if program == "sed" and any(arg.startswith(("-i", "--in-place")) for arg in args):
        paths += positional
    elif program == "perl" and any(
        arg.startswith("-") and not arg.startswith("--") and "i" in arg[1:] for arg in args
    ):
        paths += positional
    elif program in {"tee", "rm", "unlink", "truncate", "mv"}:
        paths += positional
    elif program == "cp" and positional:
        paths.append(positional[-1])
    elif program == "git":
        subcommand, rest = git_subcommand(argv)
        rest_positional = [arg for arg in rest if not arg.startswith("-")]
        if subcommand in {"rm", "mv", "restore"}:
            paths += rest_positional
        elif subcommand == "checkout" and "--" in rest:
            paths += rest[rest.index("--") + 1 :]
    return paths


def shell_writes(commands: list[tuple[list[str], str]], cwd: str) -> tuple[list[str], list[str]]:
    """這串指令寫到、還需要使用者同意的 (測試檔, 防線檔案), 路徑相對 repo 根目錄。"""
    root = repo_root(Path(cwd))
    if root is None:
        return [], []
    files = sorted(
        {
            relative(root, Path(where), path)
            for argv, where in commands
            for path in written_paths(argv)
        }
    )
    tests = pending_test_edits(root, [path for path in files if is_test_file(path)])
    return tests, protected_files.pending_protected_edits(root, files)


def with_cwd(commands: list[list[str]], cwd: str) -> list[tuple[list[str], str]]:
    """跟著 `cd` 推算每個指令的工作目錄, 相對路徑才對得到 repo 裡的檔案。"""
    result = []
    where = Path(cwd)
    for argv in commands:
        # 目錄不存在時維持原處: 之後在不存在的目錄跑 git 會讓整個 hook 出錯, 等於放行。
        if argv[0] == "cd" and len(argv) > 1 and (where / argv[1]).is_dir():
            where = where / argv[1]
        result.append((argv, str(where)))
    return result


def new_branch(argv: list[str], cwd: str) -> str | None:
    """這個指令會開始的新分支 (開分支、開 worktree、開 PR); 不是的話回傳 None。"""
    program = argv[0].rsplit("/", 1)[-1]
    if program == "gh":
        if argv[1:3] != ["pr", "create"]:
            return None
        head = [argv[i + 1] for i, arg in enumerate(argv[:-1]) if arg in {"--head", "-H"}]
        return head[0] if head else current_branch(cwd)
    if program != "git":
        return None
    subcommand, args = git_subcommand(argv)
    flags = [arg for arg in args if arg.startswith("-")]
    positional = [arg for arg in args if not arg.startswith("-")]
    if subcommand == "switch" and {"-c", "-C", "--create", "--force-create"} & set(flags):
        return positional[0] if positional else ""
    if subcommand == "checkout" and {"-b", "-B"} & set(flags):
        return positional[0] if positional else ""
    if subcommand == "branch" and not flags and positional:
        return positional[0]
    if subcommand == "worktree" and positional[:1] == ["add"]:
        named = [args[i + 1] for i, arg in enumerate(args[:-1]) if arg in {"-b", "-B"}]
        if named:
            return named[0]
        return positional[2] if len(positional) > 2 else positional[-1].rsplit("/", 1)[-1]
    return None


def parallel_branches(commands: list[tuple[list[str], str]], cwd: str) -> list[str]:
    """還有開著的 PR 時, 這串指令要開始、而且還沒被放行的分支。"""
    branches = {
        branch
        for argv, where in commands
        for branch in [new_branch(argv, where)]
        if branch is not None
    }
    root = test_lock.repo_root(Path(cwd))
    if not branches or root is None:
        return []
    pending = branches - branch_lock.approved_branches(root)
    if not pending:
        return []
    return sorted(pending) if branch_lock.open_prs(cwd) else []


def parallel_verdict(agent: str, branches: list[str]) -> tuple[str, str]:
    rule = (
        "使用者還有開著的 PR：一次只有一個進行中的 PR，合併後才開下一個"
        "（docs/workflow.md〈一次一個 PR〉）。先回報，等使用者合併；"
        "正式環境出問題要插隊，照 hotfix skill 向使用者說明並取得同意。"
    )
    if agent == "codex":
        command = " ".join([*branch_lock.APPROVE_COMMAND, *branches])
        return "deny", f"{rule}使用者同意插隊後執行 `{command}` 申請，它會請使用者確認。"
    return "ask", rule


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
    approval = self_approval(argv)
    if approval:
        return f"放行只能用 `{approval}` 申請，它會請使用者確認；不要直接寫放行檔或換寫法呼叫。"
    if bypasses_publish(argv) or (argv[0].rsplit("/", 1)[-1] == "gh" and deploys(argv)):
        return (
            f"發布 release 會直接部署，只能用 `{PUBLISH_COMMAND} <版號> [--prerelease]`，"
            "而且要先用 preview.sh 給使用者看過、使用者在對話裡同意之後才執行"
            "（.agents/skills/release/SKILL.md）。重新部署或回滾由使用者自己觸發。"
        )
    program = argv[0].rsplit("/", 1)[-1]
    if program == "git":
        return git_violation(argv, cwd)
    if program == "gh":
        return gh_violation(argv, cwd)
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


def decide(decision: str, reason: str) -> None:
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": decision,
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
        ensure_ascii=False,
    )


def main() -> int:
    agent = sys.argv[1] if len(sys.argv) > 1 else ""
    payload = json.load(sys.stdin)
    if payload.get("tool_name") != "Bash":
        return 0
    command = payload.get("tool_input", {}).get("command", "")
    cwd = payload.get("cwd") or "."
    commands = list(simple_commands(command if isinstance(command, str) else shlex.join(command)))
    located = with_cwd(commands, cwd)
    for argv, where in located:
        reason = violation(argv, where)
        if reason:
            decide("deny", reason)
            return 0
    tests, protected = shell_writes(located, cwd)
    if protected:
        decide(*protected_files.verdict(agent, protected))
        return 0
    if tests:
        decide(*verdict(agent, tests))
        return 0
    branches = parallel_branches(located, cwd)
    if branches:
        decide(*parallel_verdict(agent, branches))
        return 0
    # 發布 release 一定要使用者確認。Claude 的 permissions.ask 也會問, 這裡再回 ask 是因為
    # 權限模式 (例如自動放行) 可能略過設定檔; Codex 不支援 ask, 由 .codex/rules/ 的 prompt 負責。
    if agent == "claude" and any(argv[0] == PUBLISH_COMMAND for argv in commands):
        decide("ask", "發布 release 會直接部署：確認使用者已經看過 preview.sh 的內容並同意發布。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
