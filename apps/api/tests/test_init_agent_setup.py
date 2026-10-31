"""`make init dev` 對 AI agent 協作環境的檢查 (`scripts/lib/agent_setup.sh`)。

docs/extending/agent-hooks.md〈啟用與停用〉的每一項, 少了都不會報錯, 只是那一層檢查安靜地不生效。
能在開案時就判斷的, 在 init 擋下或提醒:
- python3 3.9 以上: hook 直接用 PATH 上的它執行, 沒有的話守衛等於不存在。擋。
- `.claude/skills` 是 symlink: Windows 沒開 core.symlinks 時 clone 成一般檔案,
  Claude 讀不到任何 skill。擋。
- 裝了 Codex 卻還沒信任這個專案: 專案的 hook、rules 與 AI_AGENT 都不會載入。
  只提醒, 不是每個人都用 Codex。

只有開發機需要: 部署主機不跑 agent、不 commit, 而且刻意只裝 Docker、make、openssl
(docs/operations.md〈生產部署〉), 所以 `make init prod` 不做這些檢查。

外部指令用假的取代: 測試不該依賴本機裝了哪個版本的 python3、有沒有裝 Codex。
住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_docs import REPO_ROOT

LIB = REPO_ROOT / "scripts" / "lib" / "agent_setup.sh"
INIT = REPO_ROOT / "scripts" / "init.sh"
BASH = shutil.which("bash") or "/bin/bash"
CHECKS = ("require_python3", "require_skills_symlink", "remind_codex_trust")


def fake_command(bin_dir: Path, name: str, script: str) -> None:
    bin_dir.mkdir(exist_ok=True)
    path = bin_dir / name
    path.write_text(f"#!/bin/sh\n{script}\n")
    path.chmod(0o755)


def run(
    command: str, cwd: Path, bin_dir: Path, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    # PATH 只放假的指令: 本機真的 python3、codex 不能混進來。不加 /bin —— Ubuntu 的 /bin 就是
    # /usr/bin, 裡面有 python3。檢查本身只用 bash 內建的指令, 不需要其他工具。
    base = {"PATH": str(bin_dir), "HOME": str(cwd)}
    # 指令是這支測試自己給的固定值, 不是外部輸入。
    return subprocess.run(  # noqa: S603
        [BASH, "-c", f'source "{LIB}"; {command}'],
        env={**base, **(env or {})},
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = (tmp_path / "repo").resolve()
    (path / ".agents" / "skills").mkdir(parents=True)
    (path / ".claude").mkdir()
    (path / ".claude" / "skills").symlink_to("../.agents/skills")
    return path


def test_dev_init_rejects_missing_python3(repo: Path, tmp_path: Path) -> None:
    result = run("require_python3", repo, tmp_path / "bin")
    assert result.returncode != 0
    assert "python3" in result.stderr


def test_dev_init_rejects_python_older_than_3_9(repo: Path, tmp_path: Path) -> None:
    # 檢查用 python3 自己判斷版本: 太舊時那段程式以非 0 結束。
    fake_command(tmp_path / "bin", "python3", "exit 1")
    result = run("require_python3", repo, tmp_path / "bin")
    assert result.returncode != 0
    assert "3.9" in result.stderr


def test_dev_init_accepts_python_3_9_or_newer(repo: Path, tmp_path: Path) -> None:
    fake_command(tmp_path / "bin", "python3", "exit 0")
    result = run("require_python3", repo, tmp_path / "bin")
    assert result.returncode == 0, result.stderr


def test_dev_init_accepts_skills_symlink(repo: Path, tmp_path: Path) -> None:
    result = run("require_skills_symlink", repo, tmp_path / "bin")
    assert result.returncode == 0, result.stderr


def test_dev_init_rejects_skills_that_are_not_a_symlink(repo: Path, tmp_path: Path) -> None:
    # core.symlinks=false 時 git 寫出的是內容為目標路徑的一般檔案。
    (repo / ".claude" / "skills").unlink()
    (repo / ".claude" / "skills").write_text("../.agents/skills")
    result = run("require_skills_symlink", repo, tmp_path / "bin")
    assert result.returncode != 0
    assert "core.symlinks" in result.stderr


def codex_config(tmp_path: Path, text: str) -> dict[str, str]:
    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "config.toml").write_text(text)
    return {"CODEX_HOME": str(home)}


def test_dev_init_reminds_to_trust_project_in_codex(repo: Path, tmp_path: Path) -> None:
    fake_command(tmp_path / "bin", "codex", "exit 0")
    other = '[projects."/somewhere/else"]\ntrust_level = "trusted"\n'
    result = run("remind_codex_trust", repo, tmp_path / "bin", codex_config(tmp_path, other))
    assert result.returncode == 0, "只提醒, 不擋"
    assert "Codex" in result.stdout
    assert "/hooks" in result.stdout


def test_dev_init_skips_codex_reminder_when_trusted(repo: Path, tmp_path: Path) -> None:
    fake_command(tmp_path / "bin", "codex", "exit 0")
    trusted = f'[projects."{repo}"]\ntrust_level = "trusted"\n'
    result = run("remind_codex_trust", repo, tmp_path / "bin", codex_config(tmp_path, trusted))
    assert result.returncode == 0
    assert not result.stdout.strip()


def test_dev_init_skips_codex_reminder_without_codex(repo: Path, tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir()
    result = run("remind_codex_trust", repo, tmp_path / "bin")
    assert result.returncode == 0
    assert not result.stdout.strip()


def branch(mode: str) -> str:
    """init.sh 結尾 case 裡 `dev)` 或 `prod)` 那一段。"""
    match = re.search(
        rf"^    {mode}\)\n(.*?)\n        ;;", INIT.read_text(encoding="utf-8"), re.M | re.S
    )
    assert match, f"init.sh 找不到 {mode}) 分支"
    return match.group(1)


def test_only_dev_init_runs_agent_setup_checks() -> None:
    dev, prod = branch("dev"), branch("prod")
    assert all(check in dev for check in CHECKS), "make init dev 要做這幾項檢查"
    assert not any(check in prod for check in CHECKS), "部署主機不需要 AI agent 的環境"
