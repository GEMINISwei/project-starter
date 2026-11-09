"""`.github/workflows/ci.yml` 的 job 結構、建置與快取。

- 每個檢查項目各自一個 job, 平行跑: 哪一項壞了從 job 名稱就看得出來, 不必等前面的項目跑完。
  每個 job 跑的仍是本機的 `make check <項目>`, CI 不另寫一份流程。
- `ci-gate` 等全部 job 跑完再判定, main 的 ruleset 只要求它 (與 pr.yml 的 `pr`)。新增或改名 job
  不必回頭改 ruleset; 反過來, 沒被 `ci-gate` 等到的 job 紅了照樣能合併, 所以 needs 要涵蓋全部。
- PR 只改了 Markdown 時 (`changes` 判定為 docs 模式) 只跑單元測試, 文件的連結與格式檢查都在裡面;
  其他 job 只在完整模式跑。判定與放行的邏輯在 `.github/scripts/`,
  見 `test_ci_mode.py`、`test_ci_gate.py`。
- deploy.yml 以 workflow_call 重用整份並傳入 tag: 每個 checkout 都要用 `inputs.ref`,
  否則部署前測的會是 main 而不是要部署的版本。
- e2e 用 gha 快取建 api 與 web, 交給 `make check e2e` 直接用 (見 `test_e2e_check.py`);
  不另開一個 job 建同樣的東西再丟掉。
- 快取 scope 與 deploy.yml 的 build 共用: 部署讀的是 CI 剛寫進去的層, 兩邊用同一組參數建,
  CI 測的與部署的才是同一份建置設定。
- e2e 依 matrix 分份 (shard): 份號與總份數經 `E2E_SHARD` 交給 `make check e2e`, 一份失敗不取消
  其他份 (各份的結果都要看到)。失敗報告的名稱帶份號, 多份時才不會互相覆蓋。
- 要裝前端套件的 job 快取 `node_modules`: key 要涵蓋 Node 版本與兩份清單, 否則命中舊快取時
  `npm ci` 該擋的 (清單與 lock 不一致、原生模組對不上 Node 版本) 都會被略過。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import re

import pytest

from tests.test_docs import REPO_ROOT

CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"

# job 名稱 → 它跑的 `make check` 項目。
CHECK_JOBS = {
    "lint": "lint",
    "contract": "contract",
    "migrate": "migrate",
    "types": "types",
    "web-test": "web-test",
    "build": "build",
    "api-test": "api-test",
    "api-integration": "integration",
    "e2e": "e2e",
}
UNIT_TEST_JOBS = {"api-test", "web-test"}
FULL_ONLY_JOBS = set(CHECK_JOBS) - UNIT_TEST_JOBS
GATE = "ci-gate"
FULL_MODE = "if: needs.changes.outputs.mode == 'full'"


def _job(workflow: str, name: str) -> str:
    match = re.search(
        rf"^  {re.escape(name)}:\n(.*?)(?=^  \S|\Z)", workflow, flags=re.MULTILINE | re.DOTALL
    )
    assert match, f"找不到 {name} job"
    return match.group(1)


def _steps(job: str) -> list[str]:
    return re.split(r"^      - ", job, flags=re.MULTILINE)[1:]


def _ci_job(name: str) -> str:
    return _job(CI_WORKFLOW.read_text(encoding="utf-8"), name)


def _ci_jobs() -> list[str]:
    jobs_section = CI_WORKFLOW.read_text(encoding="utf-8").split("\njobs:\n", 1)[1]
    return re.findall(r"^  ([a-z][\w-]*):\n", jobs_section, flags=re.MULTILINE)


def _job_key(job: str, key: str) -> str | None:
    """job 層級 (縮排 4 格) 的單行設定值。"""
    match = re.search(rf"^    {re.escape(key)}: (.+)$", job, flags=re.MULTILINE)
    return match.group(1).strip() if match else None


def _needs(job: str) -> set[str]:
    value = _job_key(job, "needs")
    if value is None:
        return set()
    return {name.strip() for name in value.strip("[]").split(",") if name.strip()}


def _build_steps(job: str) -> dict[str, str]:
    """以 context 對應 docker/build-push-action 的步驟。"""
    builds = {}
    for step in _steps(job):
        if "docker/build-push-action@" in step:
            context = re.search(r"^\s+context: (\S+)$", step, flags=re.MULTILINE)
            assert context, "build-push-action 要寫明 context"
            builds[context.group(1)] = step
    return builds


def _cache_scopes(step: str) -> set[str]:
    return set(re.findall(r"cache-(?:from|to): type=gha,scope=(\w+)", step))


def _web_jobs() -> list[str]:
    """有安裝 apps/web 套件的 job。"""
    return [name for name in _ci_jobs() if "apps/web && npm ci" in _ci_job(name)]


def test_ci_runs_each_check_as_its_own_job() -> None:
    assert set(_ci_jobs()) == {*CHECK_JOBS, "changes", GATE}
    for name, target in CHECK_JOBS.items():
        runs = [
            step
            for step in _steps(_ci_job(name))
            if re.search(rf"^run: make check {re.escape(target)}$", step, flags=re.MULTILINE)
        ]
        assert len(runs) == 1, f"{name} job 要跑 make check {target}"


def test_ci_runs_on_push_pull_request_and_workflow_call() -> None:
    # 不能手動執行: main 沒有 CI 結果時部署會自己跑一次, 失敗的 run 用 rerun 重跑。
    workflow = CI_WORKFLOW.read_text(encoding="utf-8")
    triggers = workflow.split("\non:\n", 1)[1].split("\n\n", 1)[0]
    assert re.findall(r"^  ([a-z_]+):", triggers, flags=re.MULTILINE) == [
        "push",
        "pull_request",
        "workflow_call",
    ]


def test_ci_gate_needs_every_other_job() -> None:
    assert _needs(_ci_job(GATE)) == set(_ci_jobs()) - {GATE}


def test_ci_gate_runs_even_when_needed_jobs_fail() -> None:
    # 預設上游失敗時會跳過, 被跳過的 required check 在 GitHub 上算通過。
    assert _job_key(_ci_job(GATE), "if") == "always()"


def test_full_only_jobs_run_when_mode_is_full() -> None:
    for name in FULL_ONLY_JOBS:
        job = _ci_job(name)
        assert "changes" in _needs(job), name
        assert f"    {FULL_MODE}" in job.splitlines(), name


def test_unit_test_jobs_run_in_every_mode() -> None:
    for name in UNIT_TEST_JOBS:
        assert _job_key(_ci_job(name), "if") is None, name


@pytest.mark.parametrize("name", sorted({*CHECK_JOBS, "changes", GATE}))
def test_every_ci_job_has_a_short_timeout(name: str) -> None:
    timeout = _job_key(_ci_job(name), "timeout-minutes")
    assert timeout, f"{name} job 要設 timeout-minutes"
    assert int(timeout) <= (15 if name == "e2e" else 10), name


def test_every_checkout_uses_ref_input() -> None:
    for name in _ci_jobs():
        for step in _steps(_ci_job(name)):
            if "actions/checkout@" in step:
                assert re.search(r"^\s+ref: \$\{\{ inputs\.ref \}\}$", step, flags=re.MULTILINE), (
                    name
                )


def test_migrate_job_fetches_full_history_for_tags() -> None:
    # 預設只抓一個 commit、不抓 tag: 找不到 tag 時檢查會當成「還沒發版」而略過。
    checkout = next(step for step in _steps(_ci_job("migrate")) if "actions/checkout@" in step)
    assert re.search(r"^\s+fetch-depth: 0$", checkout, flags=re.MULTILINE)


def test_ci_has_no_separate_images_job() -> None:
    assert "images" not in _ci_jobs()


def test_e2e_job_builds_images_with_gha_cache() -> None:
    builds = _build_steps(_ci_job("e2e"))
    assert set(builds) == {"apps/api", "apps/web"}
    for context, scope in (("apps/api", "api"), ("apps/web", "web")):
        step = builds[context]
        assert re.search(rf"cache-from: type=gha,scope={scope}$", step, flags=re.MULTILINE)
        assert re.search(rf"cache-to: type=gha,scope={scope},mode=max$", step, flags=re.MULTILINE)
        assert re.search(r"^\s+load: true$", step, flags=re.MULTILINE), context


def test_e2e_job_builds_same_targets_as_deploy() -> None:
    deploy = _job(DEPLOY_WORKFLOW.read_text(encoding="utf-8"), "build")
    ci_builds = _build_steps(_ci_job("e2e"))
    deploy_builds = _build_steps(deploy)
    assert set(ci_builds) == set(deploy_builds)
    for context, step in ci_builds.items():
        target = re.search(r"^\s+target: (\S+)$", step, flags=re.MULTILINE)
        deploy_target = re.search(r"^\s+target: (\S+)$", deploy_builds[context], flags=re.MULTILINE)
        assert target and deploy_target, context
        assert target.group(1) == deploy_target.group(1), context
        assert _cache_scopes(step) == _cache_scopes(deploy_builds[context]), context


def test_e2e_job_runs_make_check_e2e_with_prebuilt_images() -> None:
    job = _ci_job("e2e")
    tags = {
        context: re.search(r"^\s+tags: (\S+)$", step, flags=re.MULTILINE)
        for context, step in _build_steps(job).items()
    }
    assert all(tags.values()), "e2e 建的 image 要標 tag, make check e2e 才找得到"
    runs = [step for step in _steps(job) if re.search(r"^run: make check e2e$", step, re.MULTILINE)]
    assert len(runs) == 1
    api_tag, web_tag = tags["apps/api"], tags["apps/web"]
    assert api_tag and web_tag
    assert re.search(rf"^\s+API_IMAGE: {re.escape(api_tag.group(1))}$", runs[0], flags=re.MULTILINE)
    assert re.search(rf"^\s+WEB_IMAGE: {re.escape(web_tag.group(1))}$", runs[0], flags=re.MULTILINE)


def test_e2e_job_checks_web_image_has_only_public_salt() -> None:
    steps = [step for step in _steps(_ci_job("e2e")) if "NEXT_ACTIONS_ID_SALT" in step]
    assert len(steps) == 1, "e2e 要檢查 web image 裡只有公開的 id salt"


def test_web_jobs_cache_node_modules_by_node_and_manifests() -> None:
    # 前端的檢查都要裝套件; 至少這幾項一定在裡面, 清單才不會因為寫錯而變空。
    assert {"lint", "types", "web-test", "build"} <= set(_web_jobs())
    for name in _web_jobs():
        caches = [step for step in _steps(_ci_job(name)) if "actions/cache@" in step]
        assert len(caches) == 1, name
        assert re.search(r"^\s+path: apps/web/node_modules$", caches[0], flags=re.MULTILINE)
        key = re.search(r"^\s+key: (.+)$", caches[0], flags=re.MULTILINE)
        assert key, name
        for manifest in ("apps/web/.nvmrc", "apps/web/package.json", "apps/web/package-lock.json"):
            assert manifest in key.group(1), (name, manifest)


def test_web_jobs_skip_npm_ci_on_cache_hit() -> None:
    for name in _web_jobs():
        steps = _steps(_ci_job(name))
        cache = next(step for step in steps if "actions/cache@" in step)
        cache_id = re.search(r"^\s+id: (\S+)$", cache, flags=re.MULTILINE)
        assert cache_id, f"{name}: 快取步驟要有 id, 後面才判斷得了 cache-hit"
        npm_ci = [step for step in steps if "apps/web && npm ci" in step]
        assert len(npm_ci) == 1, name
        condition = f"if: steps.{cache_id.group(1)}.outputs.cache-hit != 'true'"
        assert condition in npm_ci[0], name


def test_e2e_job_splits_into_shards() -> None:
    job = _ci_job("e2e")
    strategy = r"^    strategy:\n(?:^      .*\n)*^      fail-fast: false$"
    assert re.search(strategy, job, flags=re.MULTILINE)
    assert re.search(r"^        shard: \[[\d, ]+\]$", job, flags=re.MULTILINE)
    runs = [step for step in _steps(job) if re.search(r"^run: make check e2e$", step, re.MULTILINE)]
    assert len(runs) == 1
    expected = "E2E_SHARD: ${{ matrix.shard }}/${{ strategy.job-total }}"
    assert re.search(rf"^\s+{re.escape(expected)}$", runs[0], flags=re.MULTILINE)


def test_e2e_report_artifact_is_named_by_shard() -> None:
    uploads = [step for step in _steps(_ci_job("e2e")) if "actions/upload-artifact@" in step]
    assert len(uploads) == 1
    name = r"^\s+name: playwright-report-\$\{\{ matrix\.shard \}\}$"
    assert re.search(name, uploads[0], flags=re.MULTILINE)
