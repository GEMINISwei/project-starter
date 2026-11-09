"""每個 app 都要有覆蓋率門檻, 而且 `docs/testing.md` 的門檻表與各 app 的設定一致。

門檻是防退步的地板: 少了它, 刪掉一整批測試也是綠燈。新增一個 app (例如背景 worker) 時最容易
漏的就是這一項, 而漏掉不會有任何症狀。門檻表寫在文件裡是給人查的, 真正生效的是設定檔,
兩邊不一致時以這支測試擋下。

認得的設定方式: Python 看 `pyproject.toml` 的 `[tool.coverage.report] fail_under`,
前端看 `vitest.config.ts` 的 `thresholds`。新的 app 用別的工具時, 在 `coverage_thresholds`
加上它的判斷方式。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import re
import tomllib
from pathlib import Path

import pytest

from tests.test_stack_scripts import REPO_ROOT

APPS = REPO_ROOT / "apps"
TESTING_DOC = REPO_ROOT / "docs" / "testing.md"
THRESHOLDS_BLOCK = re.compile(r"thresholds:\s*\{(?P<body>[^}]*)\}")
THRESHOLD_ENTRY = re.compile(r"(?P<metric>\w+):\s*(?P<value>[\d.]+)")
DOC_ROW = re.compile(r"^\| (?P<app>[\w-]+) \| (?P<metric>\w+) \| (?P<value>[\d.]+)% \|$")


def coverage_thresholds(app: Path) -> dict[str, float]:
    """回傳這個 app 的覆蓋率門檻 (指標 → 百分比); 認不出設定方式時直接讓測試失敗。"""
    pyproject = app / "pyproject.toml"
    if pyproject.exists():
        report = tomllib.loads(pyproject.read_text()).get("tool", {}).get("coverage", {})
        fail_under = report.get("report", {}).get("fail_under")
        if fail_under is not None:
            return {"statements": float(fail_under)}

    vitest = app / "vitest.config.ts"
    if vitest.exists():
        block = THRESHOLDS_BLOCK.search(vitest.read_text())
        if block:
            return {
                entry["metric"]: float(entry["value"])
                for entry in THRESHOLD_ENTRY.finditer(block["body"])
            }

    pytest.fail(
        f"apps/{app.name} 沒有覆蓋率門檻（或用了這支測試認不得的設定方式）。"
        "新增的 app 要設定覆蓋率門檻、列進 docs/testing.md 的門檻表，"
        "並在 apps/api/tests/test_coverage_thresholds.py 的 coverage_thresholds 加上它的判斷方式。"
    )


def documented_thresholds() -> dict[tuple[str, str], float]:
    """`docs/testing.md`〈覆蓋率門檻〉那一節的表格。"""
    _, found, rest = TESTING_DOC.read_text().partition("\n## 覆蓋率門檻\n")
    assert found, "docs/testing.md 少了〈覆蓋率門檻〉這一節"
    section = rest.split("\n## ", 1)[0]
    rows = (DOC_ROW.match(line) for line in section.splitlines())
    return {(row["app"], row["metric"]): float(row["value"]) for row in rows if row}


def app_dirs() -> list[Path]:
    return sorted(path for path in APPS.iterdir() if path.is_dir())


def test_every_app_has_nonzero_coverage_threshold():
    for app in app_dirs():
        thresholds = coverage_thresholds(app)
        assert thresholds, f"apps/{app.name} 的覆蓋率門檻是空的"
        # 設成 0 等於沒設: 只檢查「有沒有這個設定」的話, 填 0 就繞過去了。
        assert all(value > 0 for value in thresholds.values()), (
            f"apps/{app.name} 的覆蓋率門檻不能是 0：{thresholds}"
        )


def test_unknown_app_fails_with_instructions(tmp_path: Path):
    worker = tmp_path / "worker"
    worker.mkdir()
    (worker / "main.go").write_text("package main\n")

    with pytest.raises(pytest.fail.Exception, match=re.escape("test_coverage_thresholds.py")):
        coverage_thresholds(worker)


def test_testing_doc_lists_every_coverage_threshold():
    configured = {
        (app.name, metric): value
        for app in app_dirs()
        for metric, value in coverage_thresholds(app).items()
    }

    assert documented_thresholds() == configured


def test_web_coverage_thresholds_are_lines_and_branches_only():
    """lines 看「有沒有跑到」, branches 看「每條路有沒有走過」; 另外兩項幾乎與它們重複。"""
    assert set(coverage_thresholds(APPS / "web")) == {"lines", "branches"}
