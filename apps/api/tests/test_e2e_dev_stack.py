"""`make e2e`: 開發中反覆跑 E2E 用的常駐環境 (dev mode)。

- 每個 checkout 一套, 名稱、port 與帳密記在 git 目錄裡 (不會被 commit, 換 worktree 就是另一套),
  不碰開發中的那套, 也不碰 `make check e2e` 的拋棄式環境。
- `test` 每次先重設資料、重建超管、重啟 api (清掉行程記憶體裡的限流計數), 每次跑的起點一樣。
- 給檔案或名稱時只跑那幾個測試: 開發時要的是幾秒內知道紅綠, 完整的正式環境版本交給 CI。
  `test` 沒給檔案時拒絕, 不默默跑整套; 要整套用 `make check e2e`, 跑的是正式環境的版本, 與 CI 一致。
- 只屬於開發機, 正式環境拒絕執行。

沙盒與假的 docker 沿用 `test_stack_scripts.py`: 不碰本機真的容器, 也不讀開發者的 `.env`。
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from tests.test_stack_scripts import GIT, PASSING_TOOL, PROJECT, REPO_ROOT, Sandbox

# 記下呼叫, 與假的 docker 寫進同一份 calls, 才比得出先後。
RECORDING_NPX = '#!/bin/sh\nprintf \'npx %s\\n\' "$*" >> "$FAKE_DOCKER_DIR/calls"\n'


@pytest.fixture
def box(tmp_path: Path) -> Sandbox:
    box = Sandbox(tmp_path)
    box.write_env("development")
    shutil.copytree(REPO_ROOT / "infra", box.repo / "infra")
    (box.repo / "e2e" / "node_modules").mkdir(parents=True)
    for name in ("npm", "curl"):
        box.tool(name, PASSING_TOOL)
    box.tool("npx", RECORDING_NPX)
    box.release_checkout(tag=None)
    return box


def state(box: Sandbox) -> dict[str, str]:
    path = box.repo / ".git" / "e2e-stack.env"
    assert path.exists(), "make e2e up 要把環境記在 git 目錄裡"
    pairs = (line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)
    return dict(pairs)


def stack_running(box: Sandbox) -> None:
    box.containers(f"{state(box)['COMPOSE_PROJECT_NAME']}-api")


def test_e2e_up_starts_development_stack_under_its_own_project(box: Sandbox) -> None:
    result = box.run("e2e", "up")

    assert result.returncode == 0, result.stderr
    stack = state(box)
    assert stack["MODE"] == "development"
    assert stack["COMPOSE_PROJECT_NAME"].startswith(f"{PROJECT}-e2e-")
    assert box.called("docker-compose.dev.yml up -d")
    assert not box.called("docker-compose.prod.yml")


def test_e2e_up_keeps_stack_outside_working_tree(box: Sandbox) -> None:
    box.run("e2e", "up")

    # 指令是這支測試自己給的固定值, 不是外部輸入。
    status = subprocess.run(  # noqa: S603
        [GIT, "status", "--porcelain"], cwd=box.repo, env=box.env(), capture_output=True, text=True
    )
    assert status.stdout == ""


def test_e2e_up_again_reuses_same_stack(box: Sandbox) -> None:
    box.run("e2e", "up")
    first = state(box)

    result = box.run("e2e", "up")

    assert result.returncode == 0, result.stderr
    assert state(box) == first


def test_e2e_stacks_differ_per_checkout(box: Sandbox, tmp_path: Path) -> None:
    (tmp_path / "other").mkdir()
    other = Sandbox(tmp_path / "other")
    other.write_env("development")
    shutil.copytree(REPO_ROOT / "infra", other.repo / "infra")
    other.release_checkout(tag=None)

    box.run("e2e", "up")
    other.run("e2e", "up")

    assert state(box)["COMPOSE_PROJECT_NAME"] != state(other)["COMPOSE_PROJECT_NAME"]


def test_e2e_test_requires_stack_up(box: Sandbox) -> None:
    result = box.run("e2e", "test")

    assert result.returncode != 0
    assert "make e2e up" in result.stderr
    assert not box.called("npx playwright test")


def test_e2e_test_resets_data_and_restarts_api_before_playwright(box: Sandbox) -> None:
    box.run("e2e", "up")
    stack_running(box)

    result = box.run("e2e", "test", "auth.spec.ts")

    assert result.returncode == 0, result.stderr
    reset = box.first("db.py reset")
    migrate = box.first("db.py migrate")
    superuser = box.first("db.py create-superuser")
    restart = box.first("restart api")
    playwright = box.first("npx playwright test")
    assert reset < migrate < superuser < playwright
    assert restart < playwright


def test_e2e_test_passes_spec_files_to_playwright(box: Sandbox) -> None:
    box.run("e2e", "up")
    stack_running(box)

    result = box.run("e2e", "test", "auth.spec.ts", "users.spec.ts")

    assert result.returncode == 0, result.stderr
    assert box.called("npx playwright test auth.spec.ts users.spec.ts")


def test_e2e_test_without_specs_is_refused_before_reset(box: Sandbox) -> None:
    box.run("e2e", "up")
    stack_running(box)

    result = box.run("e2e", "test")

    assert result.returncode != 0
    assert "make check e2e" in result.stderr
    assert not box.called("db.py reset")
    assert not box.called("npx playwright test")


def test_e2e_grep_passes_name_to_playwright(box: Sandbox) -> None:
    box.run("e2e", "up")
    stack_running(box)

    result = box.run("e2e", "grep", "未登入導向 /login")

    assert result.returncode == 0, result.stderr
    assert box.called("npx playwright test --grep 未登入導向 /login")


def test_e2e_grep_requires_a_name(box: Sandbox) -> None:
    box.run("e2e", "up")
    stack_running(box)

    assert box.run("e2e", "grep").returncode != 0


def test_e2e_down_removes_stack_and_its_data(box: Sandbox) -> None:
    box.run("e2e", "up")

    result = box.run("e2e", "down")

    assert result.returncode == 0, result.stderr
    assert box.called("down -v")
    assert not (box.repo / ".git" / "e2e-stack.env").exists()


def test_e2e_down_without_stack_does_nothing(box: Sandbox) -> None:
    result = box.run("e2e", "down")

    assert result.returncode == 0, result.stderr
    assert not box.called("down")


def test_e2e_is_refused_on_production(box: Sandbox) -> None:
    box.write_env("production")

    result = box.run("e2e", "up")

    assert result.returncode != 0
    assert not box.called("up -d")


def test_e2e_rejects_unknown_subcommand(box: Sandbox) -> None:
    assert box.run("e2e", "start").returncode != 0
