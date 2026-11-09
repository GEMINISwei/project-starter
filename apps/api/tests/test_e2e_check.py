"""`make check e2e` 的拋棄式正式環境: 給了建好的 image 就直接用, 不再建一次。

CI 的 e2e job 先用 gha 快取建好 api 與 web, 再以 `API_IMAGE`/`WEB_IMAGE` 交給這支;
compose 的 `image:` 本來就讀這兩個變數 (部署也是靠它們指定 image)。
本機沒給時照舊自己建, 測的仍然是當下的原始碼。

CI 的 e2e 依 matrix 分份 (shard), 以 `E2E_SHARD=<份號>/<總份數>` 告訴這支只跑哪一份;
沒給時跑全部 (本機)。每一份把 Playwright 本身的秒數寫進 Step Summary: 何時該加份數,
看這個數字與 job 的總時間 (固定成本) 就知道, 不必猜。

沙盒與假的 docker 沿用 `test_stack_scripts.py`: 不碰本機真的容器, 也不讀開發者的 `.env`。
"""

import re
import shutil
from pathlib import Path

import pytest

from tests.test_stack_scripts import PASSING_TOOL, REPO_ROOT, Sandbox


@pytest.fixture
def box(tmp_path: Path) -> Sandbox:
    box = Sandbox(tmp_path)
    box.write_env("development")
    shutil.copytree(REPO_ROOT / "infra", box.repo / "infra")
    (box.repo / "e2e" / "node_modules").mkdir(parents=True)
    for name in ("npm", "npx", "curl"):
        box.tool(name, PASSING_TOOL)
    return box


def log_npm(box: Sandbox) -> Path:
    # 記下 npm 收到的參數, 確認 shard 有沒有傳給 Playwright。
    log = box.state / "npm-calls"
    box.tool("npm", f'#!/bin/sh\necho "$*" >> "{log}"\n')
    return log


def compose_builds(box: Sandbox) -> list[str]:
    return [call for call in box.calls() if call.startswith("compose ") and call.endswith(" build")]


def test_e2e_with_prebuilt_images_skips_compose_build(box: Sandbox) -> None:
    box.exported.update(API_IMAGE="ci-api:e2e", WEB_IMAGE="ci-web:e2e")

    result = box.run("check", "e2e")

    assert result.returncode == 0, result.stderr
    assert compose_builds(box) == []
    assert box.called("up -d")


def test_e2e_without_prebuilt_images_builds_images(box: Sandbox) -> None:
    result = box.run("check", "e2e")

    assert result.returncode == 0, result.stderr
    assert len(compose_builds(box)) == 1


def test_e2e_with_only_one_prebuilt_image_still_builds(box: Sandbox) -> None:
    # 只給一份時另一份會從原始碼建, 兩份不是同一次建置的產物; 不如照舊全部自己建。
    box.exported.update(API_IMAGE="ci-api:e2e")

    result = box.run("check", "e2e")

    assert result.returncode == 0, result.stderr
    assert len(compose_builds(box)) == 1


def test_e2e_with_shard_passes_it_to_playwright(box: Sandbox) -> None:
    log = log_npm(box)
    box.exported.update(E2E_SHARD="2/3")

    result = box.run("check", "e2e")

    assert result.returncode == 0, result.stderr
    assert any(call.endswith("--shard=2/3") for call in log.read_text().splitlines())


def test_e2e_without_shard_runs_all_tests(box: Sandbox) -> None:
    log = log_npm(box)

    result = box.run("check", "e2e")

    assert result.returncode == 0, result.stderr
    assert "--shard" not in log.read_text()


def test_e2e_writes_shard_duration_to_step_summary(box: Sandbox, tmp_path: Path) -> None:
    summary = tmp_path / "summary.md"
    box.exported.update(E2E_SHARD="2/3", GITHUB_STEP_SUMMARY=str(summary))

    result = box.run("check", "e2e")

    assert result.returncode == 0, result.stderr
    assert re.search(r"2/3.*Playwright.*\d+ 秒", summary.read_text())
