"""`.agents/hooks/` 是 Claude 與 Codex 共用的 hook 腳本, 兩份設定只負責呼叫它。

hook 是 agent 動手當下的第一道防線: 擋下 git 與 CI 看不到的事 (session 裡執行的指令),
或早一點擋下會省很多工夫的事。它不是安全機制 (指令換個寫法就可能繞過), 真正擋得住的是 git 與 CI。

兩家的 hook 協定相同: stdin 收一個 JSON, 回 `hookSpecificOutput.permissionDecision`。
所以這裡直接用 subprocess 餵 JSON 進去, 測的就是兩家實際會呼叫的那一條路。
設定檔各一份 (`.claude/settings.json` 同時是 Claude 的整份專案設定, 不能跟 Codex 共用),
兩份呼叫的腳本與事件不一致時, 只有其中一家會被擋, 而且不會報錯。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import ast
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.test_docs import REPO_ROOT

GIT = shutil.which("git") or "/usr/bin/git"
HOOKS_DIR = REPO_ROOT / ".agents" / "hooks"
GUARD = HOOKS_DIR / "guard_commands.py"
CLAUDE_SETTINGS = REPO_ROOT / ".claude" / "settings.json"
CODEX_HOOKS = REPO_ROOT / ".codex" / "hooks.json"
AGENTS = ("claude", "codex")
SCRIPT_CALL = re.compile(
    r'^python3 "\$\(git rev-parse --show-toplevel\)/(\.agents/hooks/[\w.]+\.py)" (claude|codex)$'
)


def git_repo(path: Path, branch: str) -> Path:
    subprocess.run([GIT, "init", "-q", path], check=True)  # noqa: S603
    subprocess.run(  # noqa: S603
        [GIT, "symbolic-ref", "HEAD", f"refs/heads/{branch}"], cwd=path, check=True
    )
    return path


def run_guard(agent: str, command: str, cwd: Path, tool: str = "Bash") -> dict[str, Any] | None:
    payload = {
        "hook_event_name": "PreToolUse",
        "cwd": str(cwd),
        "tool_name": tool,
        "tool_input": {"command": command},
    }
    result = subprocess.run(  # noqa: S603
        [sys.executable, GUARD, agent],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=cwd,
        check=True,
    )
    return json.loads(result.stdout) if result.stdout.strip() else None


def denied(output: dict[str, Any] | None) -> bool:
    if output is None:
        return False
    decision = output["hookSpecificOutput"]
    return bool(
        decision["hookEventName"] == "PreToolUse"
        and decision["permissionDecision"] == "deny"
        and decision["permissionDecisionReason"]
    )


@pytest.fixture
def on_feature(tmp_path: Path) -> Path:
    return git_repo(tmp_path / "repo", "feat/x")


@pytest.fixture
def on_main(tmp_path: Path) -> Path:
    return git_repo(tmp_path / "repo", "main")


BLOCKED = [
    "git push origin main",
    "git push origin HEAD:main",
    "git push -f origin feat/x:refs/heads/main",
    "git -C . push origin main",
    "cd apps && git push origin main",
    "(git push origin main)",
    'bash -c "git push origin main"',
    "gh pr merge 5 --squash",
    "npm install --force",
    "cd apps/web && npm i foo --legacy-peer-deps",
    "docker compose up -d",
    "docker --context x compose ps",
    "docker-compose logs api",
    "FOO=1 docker compose down -v",
    # 換行是指令的分隔: 第二行不是第一行的參數。
    "echo hi\ngit push origin main",
    "cat > x <<EOF\nhi\nEOF\ngit push origin main",
    "git push \\\n  origin main",
    # 跳過 git hook 等於繞過 commit-msg 的檢查。
    "git commit --no-verify -m x",
    "git commit -n -m x",
    "git commit -anm x",
    "git push --no-verify origin feat/x",
    "git -c core.hooksPath=/dev/null commit -m x",
    "git config core.hooksPath /dev/null",
    "git config --unset core.hooksPath",
]

ALLOWED = [
    "git push -u origin feat/x",
    "git push",
    "git push origin feat/x",
    'git commit -m "不要 git push origin main"',
    "gh pr view 5",
    "npm install",
    "npm run lint",
    "docker ps",
    "make services logs api",
    "echo docker compose",
    # heredoc 與 here-string 是資料, 不是指令。
    "git commit -q -F - <<'EOF'\nnever git push origin main\nEOF",
    "cat <<-EOF > notes.txt\n\tdocker compose up\n\tEOF",
    "python3 - <<'EOF'\nprint('.git/agent-approved-test-edits')\nEOF",
    "grep x <<< 'git push origin main'",
    "git push \\\n  origin feat/x",
    # push 的 -n 是 --dry-run, 不是 --no-verify。
    "git push -n origin feat/x",
    "git config core.hooksPath .githooks",
    "git config --get core.hooksPath",
]


@pytest.mark.parametrize("agent", AGENTS)
@pytest.mark.parametrize("command", BLOCKED)
def test_guard_blocks_forbidden_commands(agent: str, command: str, on_feature: Path) -> None:
    assert denied(run_guard(agent, command, on_feature)), f"沒有擋下: {command}"


@pytest.mark.parametrize("agent", AGENTS)
@pytest.mark.parametrize("command", ALLOWED)
def test_guard_allows_ordinary_commands(agent: str, command: str, on_feature: Path) -> None:
    assert run_guard(agent, command, on_feature) is None, f"誤擋: {command}"


@pytest.mark.parametrize("agent", AGENTS)
@pytest.mark.parametrize("command", ["git push", "git push origin", "git push -u origin HEAD"])
def test_guard_blocks_push_without_refspec_while_on_main(
    agent: str, command: str, on_main: Path
) -> None:
    assert denied(run_guard(agent, command, on_main)), f"在 main 上沒有擋下: {command}"


@pytest.mark.parametrize("agent", AGENTS)
def test_guard_ignores_tools_other_than_shell(agent: str, on_feature: Path) -> None:
    assert run_guard(agent, "git push origin main", on_feature, tool="Read") is None


def hook_calls(config: dict[str, Any]) -> set[tuple[str, str, str, str]]:
    """(事件, matcher, 腳本, agent 參數)。"""
    calls = set()
    for event, groups in config["hooks"].items():
        for group in groups:
            for handler in group["hooks"]:
                assert handler["type"] == "command"
                match = SCRIPT_CALL.match(handler["command"])
                assert match, f"hook 要用固定的寫法呼叫 .agents/hooks/ 的腳本: {handler['command']}"
                calls.add((event, group["matcher"], match.group(1), match.group(2)))
    return calls


def test_claude_and_codex_hook_configs_call_the_same_scripts() -> None:
    claude = hook_calls(json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8")))
    codex = hook_calls(json.loads(CODEX_HOOKS.read_text(encoding="utf-8")))
    assert claude, ".claude/settings.json 沒有任何 hook"
    assert {agent for *_, agent in claude} == {"claude"}, "Claude 的設定要帶 claude 參數"
    assert {agent for *_, agent in codex} == {"codex"}, "Codex 的設定要帶 codex 參數"
    assert {call[:3] for call in claude} == {call[:3] for call in codex}, (
        "兩份設定呼叫的事件、matcher 或腳本不一致"
    )
    missing = [script for _, _, script, _ in claude if not (REPO_ROOT / script).is_file()]
    assert not missing, f"設定呼叫了不存在的腳本: {missing}"



def test_codex_hooks_config_has_only_hooks_at_top_level() -> None:
    # Codex 0.142.5 遇到不認得的頂層欄位會讓整份設定解析失敗,
    # 兩個守衛都不載入, 只在 hooks/list 留警告
    config = json.loads(CODEX_HOOKS.read_text(encoding="utf-8"))
    assert set(config) == {"hooks"}, (
        f".codex/hooks.json 頂層只能有 hooks, 說明寫進文件: {sorted(config)}"
    )

HOOK_SCRIPTS = sorted(HOOKS_DIR.glob("*.py"))
# macOS 內建的 python3; hook 由 PATH 上的 python3 執行, 不是 api 的虛擬環境。
OLDEST_PYTHON = (3, 9)


@pytest.mark.parametrize("script", HOOK_SCRIPTS, ids=lambda path: path.name)
def test_hook_scripts_run_on_oldest_supported_python(script: Path) -> None:
    source = script.read_text(encoding="utf-8")
    # CI 用的是新版 Python, 新語法在這裡不會出錯, 只會在使用者的機器上讓 hook 安靜地失效。
    ast.parse(source, filename=script.name, feature_version=OLDEST_PYTHON)
    assert "from __future__ import annotations" in source, (
        f"{script.name}: 要加 from __future__ import annotations, `str | None` 在 3.9 上才不會出錯"
    )
