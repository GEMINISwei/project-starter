"""session 層級的 hook: 收尾前要求 make check (Stop)、開工時提示現況 (SessionStart)。

- Stop: agent 回報「做完了」之前, 程式改過卻還沒跑過 make check, 就請它先跑。make check 全部通過時
  在 .git/ 留下當時工作目錄的指紋, 指紋沒變就放行。同一輪已經被要求過 (stop_hook_active) 就不再攔,
  agent 停下來只是要問使用者問題時不會被卡住。
- SessionStart: 開新 session、恢復或壓縮後, 告訴 agent 目前的分支、開著的 PR、測試鎖的狀態,
  它才不會在等合併時順手開新分支, 或忘了實作已經開始。

兩家的格式相同 (Stop 回 decision: block, SessionStart 回 additionalContext), 所以不需要分家處理。
另外用 PATH 上的 python3 (hook 實際用的那一個) 實際跑一次每個設定的 hook: 其他測試用的是
api 的虛擬環境, 抓不到使用者機器上 python3 太舊、腳本一跑就壞的情況。
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.test_agent_hooks import CLAUDE_SETTINGS, CODEX_HOOKS, HOOKS_DIR, hook_calls
from tests.test_agent_test_guard import AGENTS, BLOCKED, decision, git, write
from tests.test_docs import REPO_ROOT
from tests.test_pr_change_checks import body, check, commit

REQUIRE_CHECK = HOOKS_DIR / "require_check.py"
SESSION_CONTEXT = HOOKS_DIR / "session_context.py"
CHECK_STAMP = HOOKS_DIR / "check_stamp.py"
CHECK_SH = REPO_ROOT / "scripts" / "check.sh"
PYTHON3 = shutil.which("python3", path="/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin")

SOURCE = "apps/api/modules/users/service.py"
TEST = "apps/api/tests/modules/users/test_service.py"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """main 上有原始碼與測試, origin/main 指向它, 目前在功能分支上、還沒有任何改動。"""
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    for name in (SOURCE, TEST, "README.md"):
        write(path, name)
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "base")
    git(path, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(path, "switch", "-q", "-c", "feat/x")
    return path


def run_hook(
    script: Path,
    agent: str,
    repo: Path,
    payload: dict[str, Any],
    env: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    payload = {"cwd": str(repo), **payload}
    result = subprocess.run(  # noqa: S603 # 執行受測的 hook
        [PYTHON3 or "python3", script, agent],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=repo,
        env=env,
        check=True,
    )
    return json.loads(result.stdout) if result.stdout.strip() else None


def stop(agent: str, repo: Path, *, active: bool = False) -> dict[str, Any] | None:
    payload = {"hook_event_name": "Stop", "stop_hook_active": active}
    return run_hook(REQUIRE_CHECK, agent, repo, payload)


def blocked(output: dict[str, Any] | None) -> bool:
    return bool(output and output.get("decision") == "block" and output.get("reason"))


def record_check(repo: Path) -> None:
    subprocess.run(  # noqa: S603 # 模擬 make check 全部通過
        [PYTHON3 or "python3", CHECK_STAMP, "record"], cwd=repo, check=True, capture_output=True
    )


@pytest.mark.parametrize("agent", AGENTS)
def test_stop_requires_check_after_code_changes(agent: str, repo: Path) -> None:
    write(repo, SOURCE, "changed\n")
    output = stop(agent, repo)
    assert blocked(output)
    assert output is not None
    assert "make check" in output["reason"]


@pytest.mark.parametrize("agent", AGENTS)
def test_stop_allows_after_successful_check(agent: str, repo: Path) -> None:
    write(repo, SOURCE, "changed\n")
    record_check(repo)
    assert stop(agent, repo) is None
    git(repo, "commit", "-q", "-am", "impl")
    record_check(repo)
    assert stop(agent, repo) is None


@pytest.mark.parametrize("agent", AGENTS)
def test_stop_requires_check_again_after_new_changes(agent: str, repo: Path) -> None:
    write(repo, SOURCE, "changed\n")
    record_check(repo)
    write(repo, SOURCE, "changed again\n")
    assert blocked(stop(agent, repo))
    write(repo, "apps/api/modules/users/new.py", "x = 1\n")
    record_check(repo)
    write(repo, "apps/api/modules/users/new.py", "x = 2\n")
    assert blocked(stop(agent, repo)), "未追蹤的檔案改過也要重跑"


@pytest.mark.parametrize("agent", AGENTS)
def test_stop_allows_commit_and_docs_changes_after_check(agent: str, repo: Path) -> None:
    # agent 的習慣是跑完檢查再 commit: commit 與只改文件不該讓它重跑幾分鐘的 make check。
    write(repo, SOURCE, "changed\n")
    record_check(repo)
    git(repo, "commit", "-q", "-am", "impl")
    assert stop(agent, repo) is None, "commit 之後"
    write(repo, "README.md", "changed\n")
    write(repo, "notes/new.md", "x\n")
    assert stop(agent, repo) is None, "只改 Markdown"
    write(repo, SOURCE, "changed again\n")
    assert blocked(stop(agent, repo)), "程式又改了"


@pytest.mark.parametrize("agent", AGENTS)
def test_stop_ignores_docs_only_changes(agent: str, repo: Path) -> None:
    assert stop(agent, repo) is None, "沒有改動"
    write(repo, "README.md", "changed\n")
    write(repo, "notes/new.md", "x\n")
    assert stop(agent, repo) is None, "只改 Markdown"


@pytest.mark.parametrize("agent", AGENTS)
def test_stop_does_not_loop_when_already_continued(agent: str, repo: Path) -> None:
    write(repo, SOURCE, "changed\n")
    assert stop(agent, repo, active=True) is None


def test_check_records_stamp_only_on_full_success() -> None:
    # 執行整套 make check 太慢, 這裡讀腳本: 只有不帶參數的 all 跑完所有步驟之後才記錄,
    # 而 set -e 讓任何一步失敗就不會走到記錄那一步。
    script = CHECK_SH.read_text(encoding="utf-8")
    assert "set -euo pipefail" in script
    lines = [line.strip() for line in script.splitlines() if "record_check_pass" in line]
    calls = [line for line in lines if not line.startswith(("#", "record_check_pass()"))]
    assert len(calls) == 1, f"只能在一個地方記錄: {calls}"
    assert re.match(r"all\)\s+run_lint;.*run_build;\s*record_check_pass\s*;;", calls[0]), calls[0]


def fake_gh(tmp_path: Path, prs: list[dict[str, Any]] | None) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "gh"
    output = f"echo '{json.dumps(prs)}'" if prs is not None else "exit 1"
    script.write_text(f"#!/bin/sh\n{output}\n", encoding="utf-8")
    script.chmod(0o755)
    return {"PATH": f"{bin_dir}:/usr/bin:/bin"}


def session_context(agent: str, repo: Path, env: dict[str, str]) -> str:
    payload = {"hook_event_name": "SessionStart", "source": "startup"}
    output = run_hook(SESSION_CONTEXT, agent, repo, payload, env)
    assert output is not None
    specific = output["hookSpecificOutput"]
    assert specific["hookEventName"] == "SessionStart"
    return str(specific["additionalContext"])


@pytest.mark.parametrize("agent", AGENTS)
def test_session_start_reports_branch_prs_and_test_lock(
    agent: str, repo: Path, tmp_path: Path
) -> None:
    prs = [{"number": 30, "headRefName": "feat/x", "isDraft": True}]
    write(repo, SOURCE, "changed\n")
    context = session_context(agent, repo, fake_gh(tmp_path, prs))
    assert "feat/x" in context
    assert "#30" in context
    assert "實作已經開始" in context


@pytest.mark.parametrize("agent", AGENTS)
def test_session_start_works_without_gh(agent: str, repo: Path, tmp_path: Path) -> None:
    context = session_context(agent, repo, fake_gh(tmp_path, None))
    assert "feat/x" in context
    assert "實作還沒開始" in context


def test_session_hooks_are_configured() -> None:
    for config in (CLAUDE_SETTINGS, CODEX_HOOKS):
        calls = {call[:3] for call in hook_calls(json.loads(config.read_text(encoding="utf-8")))}
        assert ("Stop", "", ".agents/hooks/require_check.py") in calls, config.name
        session = (
            "SessionStart",
            "startup|resume|clear|compact",
            ".agents/hooks/session_context.py",
        )
        assert session in calls, config.name


def sample_payload(event: str, matcher: str) -> dict[str, Any]:
    if event == "PreToolUse" and "Bash" in matcher.split("|"):
        return {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}
    if event == "PreToolUse":
        return {"tool_name": "Edit", "tool_input": {"file_path": "README.md"}}
    if event == "Stop":
        return {"stop_hook_active": False}
    return {"source": "startup"}


@pytest.mark.skipif(PYTHON3 is None, reason="PATH 上沒有 python3 (init 會擋下)")
@pytest.mark.parametrize("config", [CLAUDE_SETTINGS, CODEX_HOOKS], ids=lambda path: path.name)
def test_configured_hooks_run_with_python3_on_path(config: Path, repo: Path) -> None:
    for event, matcher, script, agent in hook_calls(json.loads(config.read_text("utf-8"))):
        payload = {"hook_event_name": event, **sample_payload(event, matcher)}
        result = subprocess.run(  # noqa: S603 # 用 hook 實際的直譯器跑設定裡的腳本
            [PYTHON3 or "python3", REPO_ROOT / script, agent],
            input=json.dumps({"cwd": str(repo), **payload}),
            capture_output=True,
            text=True,
            cwd=repo,
            env={"PATH": "/usr/bin:/bin"},
            check=False,
        )
        assert result.returncode == 0, f"{script} ({event}) 跑不起來: {result.stderr}"
        if result.stdout.strip():
            json.loads(result.stdout)


@pytest.mark.parametrize("path", [".agents/hooks/x.py", ".github/scripts/x.py", "scripts/check.sh"])
@pytest.mark.parametrize("agent", AGENTS)
def test_hook_and_script_changes_start_implementation(agent: str, path: str, repo: Path) -> None:
    # 它們的測試也放在 apps/api/tests/, 改了就該鎖住測試。
    write(repo, path, "changed\n")
    assert decision(agent, repo, TEST) == BLOCKED[agent]


def test_ci_and_hook_share_implementation_rule(tmp_path: Path) -> None:
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q", "-b", "main")
    commit(path, {TEST: "def test_x():\n    assert True\n", "README.md": "x\n"})
    git(path, "switch", "-q", "-c", "feat/x")
    commit(path, {".github/scripts/x.py": "x = 1\n"}, "impl")
    commit(path, {TEST: "def test_x():\n    assert 1\n"}, "change test")
    result = check(path, body())
    assert result.returncode != 0, "改 .github/scripts/ 之後才改測試, CI 也要當成實作後改測試"
    assert TEST in result.stderr
