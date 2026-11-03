"""`.github/workflows/ci.yml` 的建置與快取。

- e2e 用 gha 快取建 api 與 web, 交給 `make check e2e` 直接用 (見 `test_e2e_check.py`);
  不另開一個 job 建同樣的東西再丟掉。
- 快取 scope 與 deploy.yml 的 build 共用: 部署讀的是 CI 剛寫進去的層, 兩邊用同一組參數建,
  CI 測的與部署的才是同一份建置設定。
- check job 快取 `node_modules`: key 要涵蓋 Node 版本與兩份清單, 否則命中舊快取時
  `npm ci` 該擋的 (清單與 lock 不一致、原生模組對不上 Node 版本) 都會被略過。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import re

from tests.test_docs import REPO_ROOT

CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"


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


def test_ci_has_no_separate_images_job() -> None:
    jobs_section = CI_WORKFLOW.read_text(encoding="utf-8").split("\njobs:\n", 1)[1]
    jobs = re.findall(r"^  ([a-z][\w-]*):\n", jobs_section, flags=re.MULTILINE)
    assert "images" not in jobs


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


def test_check_job_caches_web_node_modules_by_node_and_manifests() -> None:
    caches = [step for step in _steps(_ci_job("check")) if "actions/cache@" in step]
    assert len(caches) == 1
    assert re.search(r"^\s+path: apps/web/node_modules$", caches[0], flags=re.MULTILINE)
    key = re.search(r"^\s+key: (.+)$", caches[0], flags=re.MULTILINE)
    assert key
    for manifest in ("apps/web/.nvmrc", "apps/web/package.json", "apps/web/package-lock.json"):
        assert manifest in key.group(1), manifest


def test_check_job_skips_npm_ci_on_cache_hit() -> None:
    job = _ci_job("check")
    cache = next(step for step in _steps(job) if "actions/cache@" in step)
    cache_id = re.search(r"^\s+id: (\S+)$", cache, flags=re.MULTILINE)
    assert cache_id, "快取步驟要有 id, 後面才判斷得了 cache-hit"
    npm_ci = [step for step in _steps(job) if "apps/web && npm ci" in step]
    assert len(npm_ci) == 1
    condition = f"if: steps.{cache_id.group(1)}.outputs.cache-hit != 'true'"
    assert condition in npm_ci[0]
