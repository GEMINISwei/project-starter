"""`make check api-test` 與 `make check integration`: 後端測試拆成兩份, 在 CI 上各是一個 job。

- api-test: 不需要資料庫的測試, 平行跑 (`-n auto`), 覆蓋率門檻在這裡。帶 `REQUIRE_INTEGRATION=1`:
  有 `integration` 標記的已經被 `-m` 排除, 還去連資料庫的就是忘了標記, 要失敗而不是 skip ——
  skip 的 exit code 是 0, 那批測試會在沒人發現的情況下消失。
- integration: 只跑有標記的那批, 依序跑 (共用一個資料庫), 不算覆蓋率 (門檻只在 api-test)。

沙盒與假的 docker 沿用 `test_stack_scripts.py`; uv 換成記下參數與 `REQUIRE_INTEGRATION` 的假指令。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import shutil
from pathlib import Path

import pytest

from tests.test_stack_scripts import REPO_ROOT, Sandbox

# 跟假的 docker 寫進同一份 calls, 才看得出呼叫的先後。
FAKE_UV = """#!/bin/sh
printf 'uv %s REQUIRE_INTEGRATION=%s\\n' "$*" "${REQUIRE_INTEGRATION-}" >> "$FAKE_DOCKER_DIR/calls"
exit 0
"""


@pytest.fixture
def box(tmp_path: Path) -> Sandbox:
    box = Sandbox(tmp_path)
    box.write_env("development")
    shutil.copytree(REPO_ROOT / "infra", box.repo / "infra")
    (box.repo / "apps" / "api").mkdir(parents=True, exist_ok=True)
    box.tool("uv", FAKE_UV)
    return box


def pytest_calls(box: Sandbox) -> list[str]:
    return [call for call in box.calls() if call.startswith("uv run pytest ")]


def test_check_api_test_runs_parallel_without_integration_tests(box: Sandbox) -> None:
    result = box.run("check", "api-test")

    assert result.returncode == 0, result.stderr
    [call] = pytest_calls(box)
    assert " -n auto " in f" {call} "
    assert " -m not integration " in f" {call} "
    assert " --cov " in f" {call} "
    assert call.endswith(" REQUIRE_INTEGRATION=1")


def test_check_integration_runs_only_integration_tests_without_coverage(box: Sandbox) -> None:
    result = box.run("check", "integration")

    assert result.returncode == 0, result.stderr
    [call] = pytest_calls(box)
    assert " -m integration " in f" {call} "
    assert "--cov" not in call
    assert call.endswith(" REQUIRE_INTEGRATION=1")
    assert box.called("uv run alembic check")
