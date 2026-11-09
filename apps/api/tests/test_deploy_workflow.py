"""deploy.yml: 重用 main 的 CI 結果、主機依 digest 拉 image。

- 要部署的 tag 指向的 commit 在 main 上已經跑過同一套 CI (push 觸發) 而且成功時,
  不再重跑一次 (`.github/scripts/ci-passed.sh` 判斷)。找不到就照舊先跑 CI, 判斷失敗則整次停下。
  PR 的 run 不算: 它測的是 PR 的 head, 不是 squash 之後 main 上的 commit。
- build 推完 image 後輸出 digest, 主機以 `<repo>@sha256:…` 拉: 重跑舊的部署 job 時, 組名標籤
  可能已經被之後的部署移走, 依標籤拉會拿到別版的 image 而不報錯。組名標籤照推, 清理靠它判斷。
- 每套系統的 Summary 記下它部署的 digest, 可以和主機上的 `docker inspect` 對照。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import json
import re
import shutil
import subprocess

import pytest

from tests.test_docs import REPO_ROOT

SCRIPT = REPO_ROOT / ".github" / "scripts" / "ci-passed.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
BASH = shutil.which("bash") or "/bin/bash"
SHA = "a" * 40


def ci_passed(*runs: dict[str, str], sha: str = SHA) -> subprocess.CompletedProcess[str]:
    # 輸入是 `gh api .../workflows/ci.yml/runs` 的回應格式。
    body = json.dumps({"total_count": len(runs), "workflow_runs": list(runs)})
    return subprocess.run(  # noqa: S603
        [BASH, str(SCRIPT), sha], input=body, capture_output=True, text=True, check=False
    )


def run(event: str = "push", branch: str = "main", conclusion: str = "success") -> dict[str, str]:
    return {"event": event, "head_branch": branch, "head_sha": SHA, "conclusion": conclusion}


def answer(result: subprocess.CompletedProcess[str]) -> str:
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_ci_passed_when_main_push_run_succeeded() -> None:
    assert answer(ci_passed(run())) == "true"


def test_ci_not_passed_when_only_manual_run_succeeded() -> None:
    # 只認 push 觸發的 (ci.yml 不開放手動執行), 查不到就由部署自己跑一次 CI。
    assert answer(ci_passed(run(event="workflow_dispatch"))) == "false"


def test_ci_not_passed_when_only_pull_request_runs_succeeded() -> None:
    assert answer(ci_passed(run(event="pull_request", branch="feat/x"))) == "false"


def test_ci_not_passed_when_run_is_on_another_branch() -> None:
    assert answer(ci_passed(run(branch="feat/x"))) == "false"


def test_ci_not_passed_when_main_run_did_not_succeed() -> None:
    assert answer(ci_passed(run(conclusion="failure"), run(conclusion="cancelled"))) == "false"


def test_ci_not_passed_when_run_is_for_another_commit() -> None:
    assert answer(ci_passed(run(), sha="b" * 40)) == "false"


def test_ci_passed_fails_on_unreadable_response() -> None:
    # 讀不懂 API 的回應時不能當成「沒跑過」默默重跑, 也不能當成通過。
    result = subprocess.run(  # noqa: S603
        [BASH, str(SCRIPT), SHA], input="not json", capture_output=True, text=True, check=False
    )
    assert result.returncode != 0


# ── workflow 的接法 ───────────────────────────────────────────────────────────


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _job(name: str) -> str:
    match = re.search(
        rf"^  {re.escape(name)}:\n(.*?)(?=^  \S|\Z)", _workflow(), flags=re.MULTILINE | re.DOTALL
    )
    assert match, f"deploy.yml 找不到 {name} job"
    return match.group(1)


def _needs(job: str) -> set[str]:
    match = re.search(r"^    needs: \[(.*)\]$", job, flags=re.MULTILINE)
    assert match, "沒有 needs"
    return {name.strip() for name in match.group(1).split(",")}


def _condition(job: str) -> str:
    match = re.search(r"^    if: (.*)$", job, flags=re.MULTILINE)
    assert match, "沒有 if"
    return match.group(1)


def test_version_job_outputs_commit_of_tag() -> None:
    job = _job("version")
    assert re.search(r"^      sha: \$\{\{ steps\.\S+\.outputs\.sha \}\}$", job, flags=re.MULTILINE)
    assert "git rev-parse HEAD" in job


def test_ci_result_job_asks_ci_passed_about_tag_commit() -> None:
    job = _job("ci-result")
    assert {"version"} <= _needs(job)
    assert re.search(r"^      actions: read$", job, flags=re.MULTILINE)
    assert "actions/workflows/ci.yml/runs?head_sha=" in job
    assert "needs.version.outputs.sha" in job
    assert ".github/scripts/ci-passed.sh" in job


def test_deploy_skips_ci_when_main_already_passed() -> None:
    job = _job("ci")
    assert {"version", "targets", "ci-result"} <= _needs(job)
    assert _condition(job) == "needs.ci-result.outputs.passed != 'true'"


def test_build_runs_when_ci_passed_or_was_skipped() -> None:
    job = _job("build")
    assert {"version", "targets", "ci-result", "ci"} <= _needs(job)
    assert _condition(job) == "${{ !cancelled() && !failure() }}"


def test_deploy_runs_only_after_build_and_migration_check_succeeded() -> None:
    # 上游有 job 被跳過 (ci) 時, 預設條件會把下游一起跳過, 所以寫明要哪些 job 成功。
    condition = _condition(_job("deploy"))
    assert "!cancelled()" in condition
    assert "needs.build.result == 'success'" in condition
    assert "needs.migration-check.result == 'success'" in condition


def test_build_outputs_image_digests() -> None:
    job = _job("build")
    for app in ("api", "web"):
        output = re.search(
            rf"^      {app}-digest: \$\{{\{{ steps\.(\S+)\.outputs\.digest \}}\}}$",
            job,
            flags=re.MULTILINE,
        )
        assert output, f"build 要輸出 {app}-digest"
        assert re.search(rf"^        id: {re.escape(output.group(1))}$", job, flags=re.MULTILINE)


def test_build_still_tags_group_names() -> None:
    job = _job("build")
    assert "tags: ${{ steps.names.outputs.api-tags }}" in job
    assert "tags: ${{ steps.names.outputs.web-tags }}" in job


@pytest.mark.parametrize("app", ["api", "web"])
def test_deploy_pulls_images_by_digest(app: str) -> None:
    outputs = "needs.build.outputs"
    expected = f"${{{{ {outputs}.{app}-repo }}}}@${{{{ {outputs}.{app}-digest }}}}"
    assert f"{app.upper()}_IMAGE: {expected}" in _job("deploy")


def test_deploy_summary_records_image_digests() -> None:
    steps = re.split(r"^      - ", _job("deploy"), flags=re.MULTILINE)[1:]
    summary = [step for step in steps if "GITHUB_STEP_SUMMARY" in step]
    assert len(summary) == 1, "deploy 要有一個把 digest 寫進 Summary 的步驟"
    assert "API_IMAGE" in summary[0]
    assert "WEB_IMAGE" in summary[0]
    assert "matrix.environment" in summary[0]


SSH_JOBS = ["migration-check", "deploy"]


def _steps(job: str) -> list[str]:
    return re.split(r"^      - ", _job(job), flags=re.MULTILINE)[1:]


@pytest.mark.parametrize("job", SSH_JOBS)
def test_deploy_jobs_prepare_ssh_with_shared_script(job: str) -> None:
    # 連主機前的準備只寫在 deploy-ssh.sh: 兩個 job 各寫一份時, 改了一邊另一邊會在碰主機時才失敗。
    steps = _steps(job)
    assert any(".github/scripts/deploy-ssh.sh" in step for step in steps)
    assert not any("> ~/.ssh/deploy_key" in step for step in steps)
    assert "> ~/.ssh/deploy_key" not in _workflow()


@pytest.mark.parametrize("job", SSH_JOBS)
def test_deploy_ssh_script_comes_from_workflow_commit(job: str) -> None:
    # 回滾到比 deploy-ssh.sh 還舊的 tag 時, 那個 tag 裡沒有這支腳本, 所以取 workflow 自己的 commit。
    checkouts = [
        step
        for step in _steps(job)
        if step.startswith("uses: actions/checkout@") and ".github/scripts" in step
    ]
    assert checkouts, f"{job} 要 checkout .github/scripts"
    assert all("ref:" not in step for step in checkouts)
