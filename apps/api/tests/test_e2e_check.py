"""`make check e2e` 的拋棄式正式環境: 給了建好的 image 就直接用, 不再建一次。

CI 的 e2e job 先用 gha 快取建好 api 與 web, 再以 `API_IMAGE`/`WEB_IMAGE` 交給這支;
compose 的 `image:` 本來就讀這兩個變數 (部署也是靠它們指定 image)。
本機沒給時照舊自己建, 測的仍然是當下的原始碼。

沙盒與假的 docker 沿用 `test_stack_scripts.py`: 不碰本機真的容器, 也不讀開發者的 `.env`。
"""

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
