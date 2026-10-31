"""`.githooks/commit-msg`: AI agent 做的 commit 要帶 `Co-authored-by`, 名稱寫到模型與版本。

規則在 docs/workflow.md〈AI 協作的共同作者〉。git 與 GitHub 都不強制這行, 漏了不會報錯,
之後就分不出哪些改動是哪個模型做的。git hook 是 Claude、Codex 與人都會經過的那一層。

怎麼知道是 agent 在 commit: `AI_AGENT` 環境變數 (跨工具的慣例; Claude Code 自己會設,
Codex 由專案的 `.codex/config.toml` 補上)。人自己 commit 時沒有它, 不要求 trailer。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import os
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

from tests.test_docs import REPO_ROOT

GIT = shutil.which("git") or "/usr/bin/git"
COMMIT_MSG = REPO_ROOT / ".githooks" / "commit-msg"
CODEX_CONFIG = REPO_ROOT / ".codex" / "config.toml"
TRAILER = "Co-authored-by: Claude Opus 5.5 <noreply@anthropic.com>"


def run_hook(message: str, tmp_path: Path, agent: str | None) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "COMMIT_EDITMSG"
    path.write_text(message, encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if key != "AI_AGENT"}
    if agent:
        env["AI_AGENT"] = agent
    return subprocess.run(  # noqa: S603
        [COMMIT_MSG, path], capture_output=True, text=True, env=env, cwd=tmp_path, check=False
    )


@pytest.mark.parametrize("agent", ["claude-code_2-1-309_agent", "codex"])
def test_commit_msg_rejects_agent_commit_without_coauthor(agent: str, tmp_path: Path) -> None:
    result = run_hook("feat: add x\n\n說明。\n", tmp_path, agent)
    assert result.returncode != 0
    assert "Co-authored-by" in result.stderr


@pytest.mark.parametrize(
    "trailer",
    [TRAILER, "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"],
)
def test_commit_msg_accepts_agent_commit_with_coauthor(trailer: str, tmp_path: Path) -> None:
    result = run_hook(f"feat: add x\n\n說明。\n\n{trailer}\n", tmp_path, "codex")
    assert result.returncode == 0, result.stderr


def test_commit_msg_requires_model_version_in_coauthor(tmp_path: Path) -> None:
    result = run_hook(
        "feat: add x\n\nCo-authored-by: Claude <noreply@anthropic.com>\n", tmp_path, "codex"
    )
    assert result.returncode != 0
    assert "版本" in result.stderr


def test_commit_msg_ignores_coauthor_text_outside_trailers(tmp_path: Path) -> None:
    message = f"feat: add x\n\n內文提到 {TRAILER} 不算。\n\n最後一段才是 trailer。\n"
    assert run_hook(message, tmp_path, "codex").returncode != 0


def test_commit_msg_allows_human_commits_without_coauthor(tmp_path: Path) -> None:
    assert run_hook("feat: add x\n", tmp_path, None).returncode == 0


def test_commit_msg_allows_merge_commits(tmp_path: Path) -> None:
    assert run_hook("Merge branch 'main' into feat/x\n", tmp_path, "codex").returncode == 0


def test_codex_marks_its_shell_commands_with_ai_agent() -> None:
    config = tomllib.loads(CODEX_CONFIG.read_text(encoding="utf-8"))
    assert config["shell_environment_policy"]["set"]["AI_AGENT"] == "codex"
