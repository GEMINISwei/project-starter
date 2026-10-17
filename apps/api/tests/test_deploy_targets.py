"""deploy.yml 依組名挑出要部署的 environment (`.github/scripts/deploy-targets.sh`)。

新增一套系統只要在 GitHub 建一個 environment, 所以「哪些 environment 算這一組」就是部署範圍
的唯一依據: 多算一個會把別組的系統一起更新, 少算一個則那套系統會安靜地停在舊版。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "deploy-targets.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
BASH = shutil.which("bash") or "/bin/bash"


def select(target: str, *names: str) -> subprocess.CompletedProcess[str]:
    # 參數是這支測試自己給的固定值, 不是外部輸入。
    return subprocess.run(  # noqa: S603
        [BASH, str(SCRIPT), target],
        input="".join(f"{name}\n" for name in names),
        capture_output=True,
        text=True,
        check=False,
    )


def selected(target: str, *names: str) -> list[str]:
    result = select(target, *names)
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def test_group_includes_bare_name_and_prefixed_names() -> None:
    names = ("production-b", "production", "production-a")
    assert selected("production", *names) == ["production", "production-a", "production-b"]


def test_group_excludes_other_groups() -> None:
    names = ("production-a", "staging", "staging-a", "github-pages")
    assert selected("staging", *names) == ["staging", "staging-a"]


def test_group_excludes_names_that_only_share_the_prefix() -> None:
    assert selected("production", "production-a", "productionx") == ["production-a"]


def test_group_match_ignores_case() -> None:
    # GitHub 的 environment 名稱不分大小寫, 建成大寫的也是同一組。
    assert selected("production", "Production-A") == ["Production-A"]


def test_unknown_group_fails_and_lists_available_groups() -> None:
    result = select("stagng", "production-a", "staging-a", "production-b")
    assert result.returncode != 0
    assert "production staging" in result.stderr


def test_repo_without_environments_fails() -> None:
    assert select("production").returncode != 0


@pytest.mark.parametrize("target", ["", "Production", "production-a", "prod uction", "-x"])
def test_invalid_group_name_is_rejected(target: str) -> None:
    # 組名會成為 image 標籤與 concurrency 群組, 大小寫不同會變成兩個互搶的群組。
    assert select(target, "production").returncode != 0


def _deploy_job() -> str:
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(r"^  deploy:\n(.*?)(?=^  \S|\Z)", text, flags=re.MULTILINE | re.DOTALL)
    assert match, "deploy.yml 找不到 deploy job"
    return match.group(1)


def test_deploy_keeps_other_systems_going_when_one_fails() -> None:
    # 預設的 fail-fast 會取消同組其他還在跑的系統, 可能砍在 migration 中途。
    assert re.search(r"^\s+fail-fast: false$", _deploy_job(), flags=re.MULTILINE)


def test_deploy_runs_systems_one_at_a_time() -> None:
    # 同一台主機上的多套系統同時備份、拉 image、跑 migration 會互搶資源。
    assert re.search(r"^\s+max-parallel: 1$", _deploy_job(), flags=re.MULTILINE)
