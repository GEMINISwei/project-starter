"""`make check` 的子指令: 完整的檢查只在 CI 跑, 每個 job 跑其中一項。

- 不帶參數時只印用法並失敗: 本機不一次跑全部, 失敗才不會讓人以為檢查都過了。
- 後端測試拆成 `make check api-test` 與 `make check integration`, 在 CI 上各是一個 job。

- api-test: 不需要資料庫的測試, 平行跑 (`-n auto`), 不算覆蓋率。帶 `REQUIRE_INTEGRATION=1`:
  有 `integration` 標記的已經被 `-m` 排除, 還去連資料庫的就是忘了標記, 要失敗而不是 skip ——
  skip 的 exit code 是 0, 那批測試會在沒人發現的情況下消失。
- integration: 先平行跑不需要資料庫的, 再依序跑有標記的 (共用一個資料庫), 兩段的覆蓋率合併後
  才檢查門檻 —— 只算其中一段, 存取資料庫的程式碼永遠顯示成沒測到, 退步了也看不出來。
  帶參數時只跑那幾個測試 (寫測試時確認紅燈), 不算覆蓋率也不跑 alembic check: 改了 model
  還沒寫 migration 時它一定失敗, 那不是這次要看的; 完整的版本 (CI) 照樣會檢查。
- 在 CI 上 (`GITHUB_STEP_SUMMARY` 有值) 把這次的實測值與門檻寫進 job 的 Summary。

沙盒與假的 docker 沿用 `test_stack_scripts.py`; uv 與 npm 換成記下參數的假指令,
覆蓋率的總計與前端的覆蓋率摘要由各測試放進 state 目錄。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import json
import re
import shutil
from pathlib import Path

import pytest

from tests.test_stack_scripts import REPO_ROOT, Sandbox

# 跟假的 docker 寫進同一份 calls, 才看得出呼叫的先後。
# `coverage report --format=total` 印出 state 裡的總計, 模擬合併後的覆蓋率。
FAKE_UV = """#!/bin/sh
printf 'uv %s REQUIRE_INTEGRATION=%s\\n' "$*" "${REQUIRE_INTEGRATION-}" >> "$FAKE_DOCKER_DIR/calls"
case "$*" in
    *"coverage report --format=total"*) cat "$FAKE_DOCKER_DIR/coverage-total" ;;
esac
exit 0
"""

# vitest 跑完會寫出 coverage/coverage-summary.json; 這裡從 state 複製一份, 結束碼也由 state 決定。
FAKE_NPM = """#!/bin/sh
printf 'npm %s\\n' "$*" >> "$FAKE_DOCKER_DIR/calls"
case "$*" in
    *test:coverage*)
        mkdir -p coverage
        cp "$FAKE_DOCKER_DIR/web-summary.json" coverage/coverage-summary.json
        exit "$(cat "$FAKE_DOCKER_DIR/web-exit")" ;;
esac
exit 0
"""


def web_summary(lines: float, branches: float) -> str:
    """vitest `json-summary` reporter 的輸出形狀 (只留 check.sh 會讀的欄位)。"""
    return json.dumps(
        {
            "total": {
                "lines": {"total": 100, "covered": 0, "skipped": 0, "pct": lines},
                "statements": {"total": 100, "covered": 0, "skipped": 0, "pct": 0},
                "functions": {"total": 100, "covered": 0, "skipped": 0, "pct": 0},
                "branches": {"total": 100, "covered": 0, "skipped": 0, "pct": branches},
            }
        }
    )


@pytest.fixture
def box(tmp_path: Path) -> Sandbox:
    box = Sandbox(tmp_path)
    box.write_env("development")
    shutil.copytree(REPO_ROOT / "infra", box.repo / "infra")
    (box.repo / "apps" / "api").mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO_ROOT / "apps" / "api" / "pyproject.toml", box.repo / "apps" / "api")
    shutil.copy(REPO_ROOT / "apps" / "web" / "vitest.config.ts", box.repo / "apps" / "web")
    box.tool("uv", FAKE_UV)
    box.tool("npm", FAKE_NPM)
    (box.state / "coverage-total").write_text("100.00\n")
    (box.state / "web-summary.json").write_text(web_summary(lines=100, branches=100))
    (box.state / "web-exit").write_text("0\n")
    return box


def api_threshold() -> float:
    pyproject = (REPO_ROOT / "apps" / "api" / "pyproject.toml").read_text()
    match = re.search(r"^fail_under = (\S+)", pyproject, re.MULTILINE)
    assert match, "apps/api/pyproject.toml 找不到 fail_under"
    return float(match.group(1))


def summary_lines(box: Sandbox) -> list[str]:
    summary = box.state / "summary.md"
    return summary.read_text().splitlines() if summary.exists() else []


def in_ci(box: Sandbox) -> None:
    box.exported["GITHUB_STEP_SUMMARY"] = str(box.state / "summary.md")


def pytest_calls(box: Sandbox) -> list[str]:
    return [call for call in box.calls() if call.startswith("uv run pytest ")]


def test_check_api_test_runs_parallel_without_integration_tests(box: Sandbox) -> None:
    result = box.run("check", "api-test")

    assert result.returncode == 0, result.stderr
    [call] = pytest_calls(box)
    assert " -n auto " in f" {call} "
    assert " -m not integration " in f" {call} "
    assert "--cov" not in call
    assert call.endswith(" REQUIRE_INTEGRATION=1")


def test_check_integration_measures_coverage_across_unit_and_integration_tests(
    box: Sandbox,
) -> None:
    result = box.run("check", "integration")

    assert result.returncode == 0, result.stderr
    [unit, integration] = pytest_calls(box)
    assert " -n auto " in f" {unit} "
    assert " -m not integration " in f" {unit} "
    assert " --cov " in f" {unit} "
    assert " -m integration " in f" {integration} "
    assert " --cov " in f" {integration} "
    assert " --cov-append " in f" {integration} ", "第二段要接著第一段累加, 不能把它蓋掉"
    assert all(call.endswith(" REQUIRE_INTEGRATION=1") for call in (unit, integration))


def test_check_integration_checks_coverage_threshold_before_alembic_check(box: Sandbox) -> None:
    result = box.run("check", "integration")

    assert result.returncode == 0, result.stderr
    assert box.last("uv run pytest") < box.first("uv run coverage report")
    assert box.first("uv run coverage report") < box.first("uv run alembic check")


def test_check_integration_fails_when_combined_coverage_below_threshold(box: Sandbox) -> None:
    (box.state / "coverage-total").write_text(f"{api_threshold() - 0.01:.2f}\n")

    result = box.run("check", "integration")

    assert result.returncode != 0
    assert "覆蓋率" in result.stderr
    assert not box.called("uv run alembic")


def test_check_without_target_prints_usage(box: Sandbox) -> None:
    result = box.run("check")

    assert result.returncode != 0
    assert "make check lint" in result.stderr
    assert pytest_calls(box) == []


def test_check_integration_passes_extra_args_to_pytest(box: Sandbox) -> None:
    target = "tests/shared/db/test_session.py"

    result = box.run("check", "integration", target, "-k", "rollback")

    assert result.returncode == 0, result.stderr
    [call] = pytest_calls(box)
    assert " -m integration " in f" {call} "
    assert f" {target} -k rollback " in f" {call} "
    assert " tests/ " not in f" {call} ", "帶參數時只跑指定的測試, 不要再加上整個 tests/"
    assert "--cov" not in call
    assert not box.called("uv run coverage")
    assert not box.called("uv run alembic")


def test_check_integration_writes_coverage_to_ci_summary(box: Sandbox) -> None:
    in_ci(box)
    (box.state / "coverage-total").write_text("97.50\n")

    result = box.run("check", "integration")

    assert result.returncode == 0, result.stderr
    [row] = [line for line in summary_lines(box) if line.startswith("| api ")]
    assert "97.50%" in row
    assert f"{api_threshold():g}%" in row
    assert "✅" in row


def test_check_integration_writes_coverage_to_ci_summary_when_below_threshold(
    box: Sandbox,
) -> None:
    in_ci(box)
    (box.state / "coverage-total").write_text(f"{api_threshold() - 1:.2f}\n")

    result = box.run("check", "integration")

    assert result.returncode != 0
    [row] = [line for line in summary_lines(box) if line.startswith("| api ")]
    assert f"{api_threshold() - 1:.2f}%" in row
    assert "❌" in row


def test_check_web_test_writes_coverage_to_ci_summary(box: Sandbox) -> None:
    in_ci(box)
    (box.state / "web-summary.json").write_text(web_summary(lines=96.5, branches=10))
    (box.state / "web-exit").write_text("1\n")  # vitest 低於門檻時自己會失敗

    result = box.run("check", "web-test")

    assert result.returncode != 0
    rows = {
        line.split("|")[2].strip(): line
        for line in summary_lines(box)
        if line.startswith("| web ")
    }
    assert set(rows) == {"lines", "branches"}
    assert "96.5%" in rows["lines"]
    assert "✅" in rows["lines"]
    assert "10%" in rows["branches"]
    assert "❌" in rows["branches"]


def test_check_skips_ci_summary_outside_ci(box: Sandbox) -> None:
    assert box.run("check", "integration").returncode == 0
    assert box.run("check", "web-test").returncode == 0

    assert not (box.state / "summary.md").exists()
