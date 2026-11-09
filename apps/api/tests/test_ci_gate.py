"""`.github/scripts/ci-gate.sh`: ci.yml 的總閘, 等全部 job 跑完再判定這次 CI 過不過。

main 的 ruleset 只要求 `ci-gate`, 所以「跳過」要分清楚: 被跳過的 required check 在 GitHub 上
算通過, 總閘只在 docs 模式、而且是「只在完整模式跑」的 job 被跳過時放行。其餘的跳過
(上游失敗連帶跳過、模式判斷失敗) 都算失敗。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import json
import re
import shutil
import subprocess

import pytest

from tests.test_ci_workflow import GATE, UNIT_TEST_JOBS, _ci_job, _ci_jobs, _job_key
from tests.test_docs import REPO_ROOT

SCRIPT = REPO_ROOT / ".github" / "scripts" / "ci-gate.sh"
BASH = shutil.which("bash") or "/bin/bash"
ALWAYS = ("changes", *sorted(UNIT_TEST_JOBS))
FULL_ONLY = ("lint", "build", "e2e")


def gate(mode: str, **results: str) -> subprocess.CompletedProcess[str]:
    # 輸入是 `toJSON(needs)` 的格式: job 名稱 → result 與 outputs。
    needs = {name: {"result": result, "outputs": {}} for name, result in results.items()}
    return subprocess.run(  # noqa: S603
        [BASH, str(SCRIPT), mode],
        input=json.dumps(needs),
        capture_output=True,
        text=True,
        check=False,
    )


def all_succeeded() -> dict[str, str]:
    return dict.fromkeys((*ALWAYS, *FULL_ONLY), "success")


def test_ci_gate_passes_when_all_jobs_succeeded() -> None:
    result = gate("full", **all_succeeded())
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("outcome", ["failure", "cancelled"])
@pytest.mark.parametrize("job", ["api-test", "e2e"])
def test_ci_gate_fails_when_any_job_failed_or_cancelled(job: str, outcome: str) -> None:
    for mode in ("full", "docs"):
        result = gate(mode, **{**all_succeeded(), job: outcome})
        assert result.returncode != 0, mode
        assert job in result.stderr


def test_ci_gate_fails_when_job_skipped_in_full_mode() -> None:
    result = gate("full", **{**all_succeeded(), "e2e": "skipped"})
    assert result.returncode != 0
    assert "e2e" in result.stderr


def test_ci_gate_passes_in_docs_mode_when_only_full_only_jobs_skipped() -> None:
    results = {**dict.fromkeys(ALWAYS, "success"), **dict.fromkeys(FULL_ONLY, "skipped")}
    result = gate("docs", **results)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("job", ALWAYS)
def test_ci_gate_fails_in_docs_mode_when_unit_test_job_skipped(job: str) -> None:
    results = {**dict.fromkeys(ALWAYS, "success"), **dict.fromkeys(FULL_ONLY, "skipped")}
    result = gate("docs", **{**results, job: "skipped"})
    assert result.returncode != 0
    assert job in result.stderr


@pytest.mark.parametrize("mode", ["", "unknown"])
def test_ci_gate_fails_when_mode_is_unknown(mode: str) -> None:
    # changes 失敗時 mode 是空的; 這時連「哪些可以跳過」都不知道。
    assert gate(mode, **all_succeeded()).returncode != 0


def test_ci_gate_always_required_jobs_match_workflow() -> None:
    script = SCRIPT.read_text(encoding="utf-8")
    match = re.search(r'^ALWAYS_REQUIRED="([^"]*)"$', script, flags=re.MULTILINE)
    assert match, "ci-gate.sh 要用 ALWAYS_REQUIRED 列出每種模式都要跑的 job"
    # 沒有 job 層級 if 的 job 每種模式都會跑, 總閘也要求它們一定成功。
    unconditional = {name for name in _ci_jobs() if _job_key(_ci_job(name), "if") is None}
    assert set(match.group(1).split()) == unconditional - {GATE}
