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


def run(mode: str, targets: list[str], *names: str) -> subprocess.CompletedProcess[str]:
    # 參數是這支測試自己給的固定值, 不是外部輸入。
    return subprocess.run(  # noqa: S603
        [BASH, str(SCRIPT), mode, *targets],
        input="".join(f"{name}\n" for name in names),
        capture_output=True,
        text=True,
        check=False,
    )


def selected(targets: list[str], *names: str) -> list[tuple[str, str]]:
    result = run("select", targets, *names)
    assert result.returncode == 0, result.stderr
    rows = (line.split("\t") for line in result.stdout.splitlines())
    return [(group, name) for group, name in rows]


def others(targets: list[str], *names: str) -> list[str]:
    result = run("others", targets, *names)
    assert result.returncode == 0, result.stderr
    return result.stdout.splitlines()


def test_group_includes_bare_name_and_prefixed_names() -> None:
    assert selected(["production"], "production-b", "production", "production-a") == [
        ("production", "production"),
        ("production", "production-a"),
        ("production", "production-b"),
    ]


def test_group_excludes_other_groups() -> None:
    names = ("production-a", "staging", "staging-a", "github-pages")
    assert selected(["staging"], *names) == [("staging", "staging"), ("staging", "staging-a")]


def test_several_groups_are_selected_together() -> None:
    names = ("production-a", "canary-a", "staging-a")
    assert selected(["staging", "canary"], *names) == [
        ("canary", "canary-a"),
        ("staging", "staging-a"),
    ]


def test_repeated_group_is_deployed_once() -> None:
    assert selected(["canary", "canary"], "canary-a") == [("canary", "canary-a")]


def test_group_excludes_names_that_only_share_the_prefix() -> None:
    assert selected(["production"], "production-a", "productionx") == [
        ("production", "production-a")
    ]


def test_group_match_ignores_case() -> None:
    # GitHub 的 environment 名稱不分大小寫, 建成大寫的也是同一組。
    assert selected(["production"], "Production-A") == [("production", "Production-A")]


def test_any_unknown_group_fails_the_whole_selection() -> None:
    # 一組打錯時其他組也不部署: 否則結果看起來成功, 漏掉的那組沒人發現。
    result = run("select", ["production", "stagng"], "production-a", "staging-a")
    assert result.returncode != 0
    assert result.stdout == ""
    assert "stagng" in result.stderr
    assert "production staging" in result.stderr


def test_repo_without_environments_fails() -> None:
    assert run("select", ["production"]).returncode != 0


def test_selecting_no_group_fails() -> None:
    assert run("select", [], "production").returncode != 0


@pytest.mark.parametrize("target", ["", "Production", "production-a", "prod uction", "-x"])
def test_invalid_group_name_is_rejected(target: str) -> None:
    # 組名會成為 image 標籤, 大小寫不同會變成兩個標籤, 主機拉到的不是這次建的那份。
    assert run("select", [target], "production").returncode != 0


def test_others_lists_groups_not_selected() -> None:
    names = ("production-a", "staging-a", "canary-a", "canary-b", "demo")
    assert others(["production"], *names) == ["canary", "demo", "staging"]


def test_others_is_empty_when_every_group_is_selected() -> None:
    assert others(["production", "staging"], "production-a", "staging-a") == []


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _deploy_job() -> str:
    match = re.search(r"^  deploy:\n(.*?)(?=^  \S|\Z)", _workflow(), flags=re.MULTILINE | re.DOTALL)
    assert match, "deploy.yml 找不到 deploy job"
    return match.group(1)


def test_release_triggers_once_per_publish() -> None:
    # `published` 在發布正式版時會和 `released` 一起觸發, 同一個版本就會部署兩次;
    # 只聽 prereleased 與 released, pre-release 改成正式版時也才會部署到正式版的組。
    assert re.search(r"^    types: \[prereleased, released\]$", _workflow(), flags=re.MULTILINE)


def test_ci_waits_for_tag_and_targets_checks() -> None:
    # 兩者任一失敗都不會部署, CI 不該先跑起來白花幾分鐘。
    match = re.search(r"^  ci:\n(.*?)(?=^  \S|\Z)", _workflow(), flags=re.MULTILINE | re.DOTALL)
    assert match, "deploy.yml 找不到 ci job"
    assert re.search(r"^    needs: \[version, targets\]$", match.group(1), flags=re.MULTILINE)


def test_deploy_keeps_other_systems_going_when_one_fails() -> None:
    # 預設的 fail-fast 會取消同組其他還在跑的系統, 可能砍在 migration 中途。
    assert re.search(r"^\s+fail-fast: false$", _deploy_job(), flags=re.MULTILINE)


def test_deploy_runs_systems_one_at_a_time() -> None:
    # 同一台主機上的多套系統同時備份、拉 image、跑 migration 會互搶資源。
    assert re.search(r"^\s+max-parallel: 1$", _deploy_job(), flags=re.MULTILINE)


def _job(name: str) -> str:
    match = re.search(
        rf"^  {re.escape(name)}:\n(.*?)(?=^  \S|\Z)", _workflow(), flags=re.MULTILINE | re.DOTALL
    )
    assert match, f"deploy.yml 找不到 {name} job"
    return match.group(1)


def test_deploy_waits_for_migration_check_of_every_system() -> None:
    """整組都通過方向檢查才開始部署任何一套; 獨立的 job, 所以也在備份與 checkout 之前。

    檢查放在各自的部署 job 裡的話, 可能前幾套已經回滾、後面的被拒絕, 同一組跑著不同版本。
    """
    needs = re.search(r"^    needs: \[(.*)\]$", _deploy_job(), flags=re.MULTILINE)
    assert needs, "deploy job 沒有 needs"
    assert "migration-check" in [job.strip() for job in needs.group(1).split(",")]
    check = _job("migration-check")
    assert "matrix: ${{ fromJSON(needs.targets.outputs.matrix) }}" in check
    assert "environment: ${{ matrix.environment }}" in check


def test_targets_summary_lists_groups_not_deployed() -> None:
    # 部署結果看 job 列表就夠, 但沒列在這次的組 (例如 Variable 漏設) 在列表上看不出來,
    # 只有 targets 知道, 所以由它寫進 Summary。
    step = re.search(r"^          \{\n(.*?)^          \} >> \"\$\{GITHUB_STEP_SUMMARY\}\"$",
                     _job("targets"), flags=re.MULTILINE | re.DOTALL)
    assert step, "targets job 沒有寫 Summary"
    assert "這次沒有部署的組" in step.group(1)
    assert "${others}" in step.group(1)


def _host_script() -> list[str]:
    match = re.search(r"- name: 部署到主機\n(.*?)(?=^      - |\Z)", _deploy_job(),
                      flags=re.MULTILINE | re.DOTALL)
    assert match, "deploy job 找不到「部署到主機」"
    return match.group(1).splitlines()


@pytest.mark.parametrize(
    "command",
    ["make backup allow-fresh", "git checkout", "docker login", "make start", "make services"],
)
def test_deploy_reports_failed_host_step_as_error(command: str) -> None:
    # 主機上整段腳本只回一個 exit code, Annotations 只會寫 exit code 1; 每一步先記下名稱,
    # 失敗時由 ERR trap 印成 ::error::, 不必點進 log 就知道停在哪。
    lines = _host_script()
    assert any("trap" in line and "::error::" in line and "ERR" in line for line in lines)
    index = next((i for i, line in enumerate(lines) if command in line), None)
    assert index is not None, f"「部署到主機」裡找不到 {command}"
    assert "step=" in lines[index - 1], f"{command} 之前沒有記下步驟名稱"


def test_deploy_reports_ssh_connection_failure_as_error() -> None:
    # ssh 連不上時以 255 結束, 主機端的 trap 根本沒機會跑。
    script = "\n".join(_host_script())
    assert re.search(r"255.*::error::", script)


def test_migration_check_uses_target_tag() -> None:
    check = _job("migration-check")
    assert "ref: refs/tags/${{ needs.version.outputs.tag }}" in check
    assert "make db revision" in check
    assert "check_migration_direction" in check
