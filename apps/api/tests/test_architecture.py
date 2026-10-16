"""import-linter 管不到的結構規則。

依賴方向 (app → modules → shared、跨模組只走 public) 由 import-linter 檢查, 設定在
pyproject.toml 的 `[tool.importlinter]`。這裡放 import-linter 管不到的: 「哪些套件不該存在」,
以及 tests/ 的依賴方向。
"""

import ast
from pathlib import Path

SRC = Path(__file__).parents[1]


def test_no_horizontal_layer_packages():
    # 功能是垂直切分的; 開了水平層就會開始有「所有 service 放一起」的東西。
    forbidden = {"api", "core", "framework", "repositories", "services"}
    found = sorted(
        name for name in forbidden if (SRC / name).is_dir() or (SRC / f"{name}.py").exists()
    )
    assert found == []


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_shared_tests_do_not_depend_on_the_project():
    """`shared/` 要能連同 `tests/shared/` 整包複製到別的專案, 所以那批測試不可以碰
    `app`/`modules`。import-linter 只看原始碼, 管不到 tests/, 這條補上。

    涵蓋函式裡的延遲 import (`ast.walk` 走整棵樹) —— 那正是最容易漏看的寫法。
    """
    offenders = sorted(
        f"{path.relative_to(SRC)}: {sorted(roots)}"
        for path in (SRC / "tests" / "shared").rglob("*.py")
        if (roots := _imported_roots(path) & {"app", "modules"})
    )
    assert offenders == []


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
