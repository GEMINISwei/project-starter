"""`.githooks/commit-msg`: AI agent 做的 commit 要帶 `Co-authored-by`, 名稱寫到模型與版本。

規則在 docs/workflow.md〈AI 協作的共同作者〉。git 與 GitHub 都不強制這行, 漏了不會報錯,
之後就分不出哪些改動是哪個模型做的。git hook 是 Claude、Codex 與人都會經過的那一層。

怎麼知道是 agent 在 commit: `AI_AGENT` 環境變數 (跨工具的慣例; Claude Code 自己會設,
Codex 由專案的 `.codex/config.toml` 補上)。人自己 commit 時沒有它, 不要求 trailer。

另一條對所有人都適用: 訊息裡不能有 GitHub 的 CI 略過標記。GitHub 在整份訊息裡找它, 而 squash
預設把分支上每個 commit 的訊息都併進 main 的 commit, 只要一個 commit 帶著它, main 就不跑 CI
(部署也會因此找不到 main 的 CI 結果)。要略過某些檢查時寫成 workflow 的條件, 不靠訊息。

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


SKIP_MARKERS = [
    "[skip ci]",
    "[ci skip]",
    "[no ci]",
    "[skip actions]",
    "[actions skip]",
    "[Skip CI]",
]


@pytest.mark.parametrize("marker", SKIP_MARKERS)
@pytest.mark.parametrize("agent", ["codex", None])
def test_commit_msg_rejects_ci_skip_marker_in_title(
    marker: str, agent: str | None, tmp_path: Path
) -> None:
    result = run_hook(f"test: add x {marker}\n\n{TRAILER}\n", tmp_path, agent)
    assert result.returncode != 0
    assert "main" in result.stderr


@pytest.mark.parametrize("agent", ["codex", None])
def test_commit_msg_rejects_ci_skip_marker_in_body(agent: str | None, tmp_path: Path) -> None:
    message = f"feat: add x\n\n說明裡提到 [skip ci] 也一樣會被 GitHub 認到。\n\n{TRAILER}\n"
    assert run_hook(message, tmp_path, agent).returncode != 0


# GitHub 另一種略過寫法: 訊息最後空兩行接這個 trailer, 一樣讓 push 與 PR 的 workflow 都不跑。
@pytest.mark.parametrize("trailer", ["skip-checks: true", "skip-checks:true"])
@pytest.mark.parametrize("agent", ["codex", None])
def test_commit_msg_rejects_skip_checks_trailer(
    trailer: str, agent: str | None, tmp_path: Path
) -> None:
    message = f"feat: add x\n\n說明。\n\n{TRAILER}\n\n\n{trailer}\n"
    result = run_hook(message, tmp_path, agent)
    assert result.returncode != 0
    assert "main" in result.stderr


def test_commit_msg_ignores_ci_skip_marker_in_comments_and_verbose_diff(tmp_path: Path) -> None:
    # git 會在送出前拿掉 # 開頭的行與 `commit -v` 剪刀線之後的 diff, 那些不會進 commit。
    message = (
        f"feat: add x\n\n{TRAILER}\n"
        "# 註解提到 [skip ci]\n"
        "# ------------------------ >8 ------------------------\n"
        '+    marker = "[skip ci]"\n'
    )
    result = run_hook(message, tmp_path, "codex")
    assert result.returncode == 0, result.stderr


def test_codex_marks_its_shell_commands_with_ai_agent() -> None:
    config = tomllib.loads(CODEX_CONFIG.read_text(encoding="utf-8"))
    assert config["shell_environment_policy"]["set"]["AI_AGENT"] == "codex"
