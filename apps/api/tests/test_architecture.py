"""靜態守住 app → modules → shared 的依賴方向。"""

import ast
from pathlib import Path

SRC = Path(__file__).parents[1]

# 只走訪這三個套件根，不是整個 app 目錄。`tests/` 與 `scripts/` 就住在同一層，
# 把它們掃進來會產生大量假陽性 —— `tests/modules/items/…` 對別的模組的 import
# 是測試該有的行為，不是跨模組深入引用。
PACKAGE_DIRS = ("app", "modules", "shared")

# module 對外只有這兩個名字：`public` 給執行期用，`manifest` 給組裝用。
PUBLIC_ENTRYPOINTS = {"public", "manifest"}


def _package_parts(path: Path) -> list[str]:
    """檔案所屬套件的路徑片段，例如 `modules/items/service.py` -> `['modules', 'items']`。"""
    return list(path.relative_to(SRC).parts[:-1])


def _imports(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = _package_parts(path)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    yield node.module
                continue

            # 相對 import 也要檢查。`from ..users.model import UserTable` 是不折不扣的
            # 跨模組深入引用，只是寫法不同 —— 直接略過所有相對 import 會讓底下的規則
            # 全部被繞開。這裡解析成絕對名稱後，套用的是同一組規則。
            base = package[: max(0, len(package) - (node.level - 1))]
            resolved = [*base, node.module] if node.module else base
            if resolved:
                yield ".".join(resolved)


def test_shared_has_no_application_or_feature_dependencies():
    violations: list[str] = []
    for path in (SRC / "shared").rglob("*.py"):
        for imported in _imports(path):
            if imported == "app" or imported.startswith(("app.", "modules.")):
                violations.append(f"{path.relative_to(SRC)} -> {imported}")
    assert violations == []


def test_cross_module_imports_use_public_entrypoints():
    violations: list[str] = []
    for path in (SRC / "modules").rglob("*.py"):
        source_module = path.relative_to(SRC / "modules").parts[0]
        for imported in _imports(path):
            if not imported.startswith("modules."):
                continue
            parts = imported.split(".")
            target_module = parts[1]
            if target_module != source_module and parts[2:] != ["public"]:
                violations.append(f"{path.relative_to(SRC)} -> {imported}")
    assert violations == []


def test_modules_only_import_declared_application_contracts():
    # 只剩 `app.permissions` 一個例外，理由是 `Permission` enum 必須是所有 module 的聯集
    # 才能進 OpenAPI（見 docs/architecture.md「三份刻意中央化的清單」）。
    # manifest 契約本身已經搬到 `shared/module.py` —— 它不是組裝，不該在這份清單裡。
    allowed = {"app.permissions"}
    violations: list[str] = []
    for path in (SRC / "modules").rglob("*.py"):
        for imported in _imports(path):
            if imported == "app" or (imported.startswith("app.") and imported not in allowed):
                violations.append(f"{path.relative_to(SRC)} -> {imported}")
    assert violations == []


def test_app_layer_only_imports_module_public_entrypoints():
    """組裝層跟其他 module 一樣只能走公開面。

    少了這條，`app/` 可以直接指進某個 module 的 service 或 schema，module 的內部結構
    就不再能安全重整 —— 而那正是模組化要換來的東西。
    """
    violations: list[str] = []
    for path in (SRC / "app").rglob("*.py"):
        for imported in _imports(path):
            if not imported.startswith("modules."):
                continue
            parts = imported.split(".")
            if len(parts) < 3 or parts[2] not in PUBLIC_ENTRYPOINTS:
                violations.append(f"{path.relative_to(SRC)} -> {imported}")
    assert violations == []


def test_horizontal_layer_packages_are_not_imported():
    forbidden = ("api", "core", "framework", "repositories", "services")
    violations: list[str] = []
    # `main.py` 也要檢查。它是唯一不住在套件裡的原始碼，漏掉的話入口點就成了規則的破口。
    package_files = (p for name in PACKAGE_DIRS for p in (SRC / name).rglob("*.py"))
    forbidden_prefixes = tuple(f"{name}." for name in forbidden)
    for path in (SRC / "main.py", *package_files):
        for imported in _imports(path):
            if imported in forbidden or imported.startswith(forbidden_prefixes):
                violations.append(f"{path.relative_to(SRC)} -> {imported}")
    assert violations == []
