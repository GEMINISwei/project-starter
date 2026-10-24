"""import-linter 管不到的結構規則。

依賴方向 (app → modules → shared、跨模組只走 public) 由 import-linter 檢查, 設定在
pyproject.toml 的 `[tool.importlinter]`。這裡放 import-linter 管不到的: 「哪些套件不該存在」、
它的掃描範圍是否涵蓋所有原始碼, 以及 tests/ 的結構。
"""

import tomllib
from pathlib import Path

SRC = Path(__file__).parents[1]


def test_no_horizontal_layer_packages():
    # 功能是垂直切分的; 開了水平層就會開始有「所有 service 放一起」的東西。
    forbidden = {"api", "core", "framework", "repositories", "services"}
    found = sorted(
        name for name in forbidden if (SRC / name).is_dir() or (SRC / f"{name}.py").exists()
    )
    assert found == []


# 不受邊界規則管的頂層目錄: 測試、CLI 腳本與 migration 都不是被 import 的原始碼。
NOT_SOURCE_DIRS = {"tests", "scripts", "migrations"}


def test_every_source_package_is_checked_by_import_linter():
    """新增的頂層套件沒加進 `root_packages` 的話, 那一層不受邊界規則管, 而且不會報錯。"""
    config = tomllib.loads((SRC / "pyproject.toml").read_text(encoding="utf-8"))
    checked = set(config["tool"]["importlinter"]["root_packages"])
    packages = {
        directory.name
        for directory in SRC.iterdir()
        if directory.is_dir()
        and not directory.name.startswith((".", "_"))
        and directory.name not in NOT_SOURCE_DIRS
        and any(directory.rglob("*.py"))
    }
    assert sorted(packages - checked) == []


def test_test_packages_mirror_the_source():
    """`tests/` 底下的每個子目錄都要對應到同名的原始碼目錄 (與原始碼同構)。

    測試放錯目錄不會報錯, 只會讓「這個套件有沒有測試」變得找不到; 刪掉一個 module 時,
    對應的測試目錄也才會跟著被整包刪掉, 而不是留下引用不到東西的測試。
    """
    tests_root = SRC / "tests"
    strays = sorted(
        str(directory.relative_to(tests_root))
        for directory in tests_root.rglob("*")
        if directory.is_dir()
        and directory.name != "__pycache__"
        and not (SRC / directory.relative_to(tests_root)).is_dir()
    )
    assert strays == []
