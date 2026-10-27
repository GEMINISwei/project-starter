"""deploy.yml 的 cleanup-ghcr: 部署完清掉 GHCR 上沒有標籤的舊版本, 再確認每個標籤都還完整。

回滾是從 git tag 重建, 舊版本沒有用處, 但清理工具一旦誤刪 (例如 attestation 底下的 image 本體,
在 GHCR 上也顯示成 untagged), 主機下次部署或 Re-run 就拉不到 image, 而且刪除不可逆。
驗證由 `.github/scripts/ghcr-verify.sh` 做, 這裡用假的 curl 模擬 registry。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "ghcr-verify.sh"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
BASH = shutil.which("bash") or "/bin/bash"

IMAGE = "ghcr.io/owner/repo-api"
INDEX = "application/vnd.oci.image.index.v1+json"
MANIFEST = "application/vnd.oci.image.manifest.v1+json"

# 依 URL 的路徑回應, 找不到就跟 `curl -f` 遇到 404 一樣以 22 結束。
FAKE_CURL = """#!/usr/bin/env bash
for arg in "$@"; do
    case "$arg" in https://*) url="$arg" ;; esac
done
key="$(printf '%s' "${url#https://ghcr.io/}" | tr -c 'A-Za-z0-9' '_')"
[ -f "${FIXTURES}/${key}" ] || exit 22
cat "${FIXTURES}/${key}"
"""


class Registry:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.fixtures = root / "fixtures"
        self.fixtures.mkdir()
        bin_dir = root / "bin"
        bin_dir.mkdir()
        curl = bin_dir / "curl"
        curl.write_text(FAKE_CURL, encoding="utf-8")
        curl.chmod(0o755)
        self.bin = bin_dir
        self.summary = root / "summary.md"

    def _put(self, path: str, body: object) -> None:
        key = re.sub(r"[^A-Za-z0-9]", "_", path)
        self.fixtures.joinpath(key).write_text(json.dumps(body), encoding="utf-8")

    def repo(self, repo: str, tags: list[str]) -> None:
        self._put(f"token?scope=repository:{repo}:pull", {"token": "t"})
        self._put(f"v2/{repo}/tags/list", {"name": repo, "tags": tags})

    def index(self, repo: str, ref: str, children: list[str]) -> None:
        manifests = [{"digest": child, "mediaType": MANIFEST} for child in children]
        self._put(f"v2/{repo}/manifests/{ref}", {"mediaType": INDEX, "manifests": manifests})

    def manifest(self, repo: str, ref: str) -> None:
        self._put(f"v2/{repo}/manifests/{ref}", {"mediaType": MANIFEST, "layers": []})

    def verify(self, *images: str) -> subprocess.CompletedProcess[str]:
        env = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "FIXTURES": str(self.fixtures),
            "GITHUB_ACTOR": "actor",
            "GITHUB_TOKEN": "token",
            "GITHUB_STEP_SUMMARY": str(self.summary),
        }
        # 參數是這支測試自己給的固定值, 不是外部輸入。
        return subprocess.run(  # noqa: S603
            [BASH, str(SCRIPT), *images], capture_output=True, text=True, check=False, env=env
        )


@pytest.fixture
def registry(tmp_path: Path) -> Registry:
    return Registry(tmp_path)


def _complete(registry: Registry, repo: str, tag: str, prefix: str) -> None:
    registry.index(repo, tag, [f"sha256:{prefix}1", f"sha256:{prefix}2"])
    registry.manifest(repo, f"sha256:{prefix}1")
    registry.manifest(repo, f"sha256:{prefix}2")


def test_verify_passes_when_every_tag_is_complete(registry: Registry) -> None:
    registry.repo("owner/repo-api", ["production", "staging"])
    _complete(registry, "owner/repo-api", "production", "a")
    _complete(registry, "owner/repo-api", "staging", "b")
    result = registry.verify(IMAGE)
    assert result.returncode == 0, result.stdout + result.stderr
    summary = registry.summary.read_text(encoding="utf-8")
    assert "production" in summary
    assert "staging" in summary


def test_verify_accepts_single_manifest_image(registry: Registry) -> None:
    # build 時關掉 provenance 的話標籤直接指向 image, 沒有子 manifest 要確認。
    registry.repo("owner/repo-api", ["production"])
    registry.manifest("owner/repo-api", "production")
    result = registry.verify(IMAGE)
    assert result.returncode == 0, result.stdout + result.stderr


def test_verify_fails_when_a_tagged_index_lost_a_manifest(registry: Registry) -> None:
    registry.repo("owner/repo-api", ["production"])
    registry.index("owner/repo-api", "production", ["sha256:a1", "sha256:a2"])
    registry.manifest("owner/repo-api", "sha256:a2")
    result = registry.verify(IMAGE)
    assert result.returncode == 1
    errors = [line for line in result.stdout.splitlines() if line.startswith("::error::")]
    assert errors, result.stdout
    assert "production" in errors[0]
    assert "sha256:a1" in errors[0]


def test_verify_checks_tags_of_groups_not_deployed(registry: Registry) -> None:
    # 只部署 production 時, staging 的 image 被誤刪也要在這次被發現。
    registry.repo("owner/repo-api", ["production", "staging"])
    _complete(registry, "owner/repo-api", "production", "a")
    registry.index("owner/repo-api", "staging", ["sha256:b1"])
    result = registry.verify(IMAGE)
    assert result.returncode == 1
    assert "staging" in result.stdout


def test_verify_fails_when_tags_cannot_be_listed(registry: Registry) -> None:
    result = registry.verify(IMAGE)
    assert result.returncode != 0
    assert "::error::" in result.stdout


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _job(name: str) -> str:
    match = re.search(
        rf"^  {re.escape(name)}:\n(.*?)(?=^  \S|\Z)", _workflow(), flags=re.MULTILINE | re.DOTALL
    )
    assert match, f"deploy.yml 找不到 {name} job"
    return match.group(1)


def _steps(job: str) -> list[str]:
    return re.split(r"^      - ", job, flags=re.MULTILINE)[1:]


def _cleanup_step() -> str:
    steps = [step for step in _steps(_job("cleanup-ghcr")) if "ghcr-cleanup-action@" in step]
    assert len(steps) == 1, "cleanup-ghcr 要剛好有一個清理步驟"
    return steps[0]


def test_ghcr_cleanup_runs_after_deploy_once_build_pushed() -> None:
    # 部署完才清: 這次部署拉 image 時不會碰到清理。deploy 失敗也照樣清, image 已經 push 了;
    # build 沒成功就不清, GHCR 維持原狀。
    job = _job("cleanup-ghcr")
    needs = re.search(r"^    needs: \[(.*)\]$", job, flags=re.MULTILINE)
    assert needs, "cleanup-ghcr 沒有 needs"
    assert {"build", "deploy"} <= {name.strip() for name in needs.group(1).split(",")}
    condition = re.search(r"^    if: \$\{\{ (.*) \}\}$", job, flags=re.MULTILINE)
    assert condition, "cleanup-ghcr 沒有 if"
    assert "!cancelled()" in condition.group(1)
    assert "needs.build.result == 'success'" in condition.group(1)


def test_ghcr_cleanup_only_deletes_untagged() -> None:
    step = _cleanup_step()
    assert re.search(r"^\s+delete-untagged: true$", step, flags=re.MULTILINE)
    for option in ("delete-tags", "tags", "keep-n-tagged", "older-than", "delete-partial-images"):
        assert not re.search(rf"^\s+{option}:", step, flags=re.MULTILINE), option


def test_ghcr_cleanup_failure_is_only_a_warning() -> None:
    # 清理失敗只是 GHCR 多留幾份, 下次部署會一起清; 驗證失敗代表 registry 上的 image 壞了, 要變紅。
    assert re.search(r"^\s+continue-on-error: true$", _cleanup_step(), flags=re.MULTILINE)
    verify = [step for step in _steps(_job("cleanup-ghcr")) if "ghcr-verify.sh" in step]
    assert len(verify) == 1, "cleanup-ghcr 要有一個驗證步驟"
    assert "continue-on-error" not in verify[0]
    assert "continue-on-error" not in _job("cleanup-ghcr").split("steps:")[0]


def test_ghcr_cleanup_action_is_pinned_to_sha() -> None:
    # 它拿得到能刪 package 的 token, tag 被改指向別的 commit 時不能跟著跑。
    assert re.search(r"uses: dataaxiom/ghcr-cleanup-action@[0-9a-f]{40} # v", _cleanup_step())


def test_only_build_and_cleanup_can_write_packages() -> None:
    jobs_section = _workflow().split("\njobs:\n", 1)[1]
    jobs = re.findall(r"^  ([a-z][\w-]*):\n", jobs_section, flags=re.MULTILINE)
    writers = {
        job for job in jobs if re.search(r"^      packages: write$", _job(job), flags=re.MULTILINE)
    }
    assert writers == {"build", "cleanup-ghcr"}
