"""`docs/features/` 的索引與段落。

功能文件只描述「現在」怎麼運作, 主題各不相同, 所以只固定開頭與結尾: 一打開就知道涵蓋什麼,
最後一段一定能跳到實作與守住行為的測試。中間的標題依主題命名, 那才是讀者要找的內容。

連結與錨點由 `test_docs.py` 檢查, 這裡只管功能文件自己的規則。
"""

import re
from pathlib import Path

import pytest

from tests.test_docs import INLINE_CODE, REPO_ROOT, links, prose, split

FEATURES_DIR = REPO_ROOT / "docs" / "features"
INDEX = FEATURES_DIR / "README.md"
TEMPLATE = FEATURES_DIR / "_template.md"
FEATURES = sorted(path for path in FEATURES_DIR.glob("*.md") if path not in {INDEX, TEMPLATE})
FILENAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*\.md$")
CODE_AND_TESTS = "程式與測試"
H2 = re.compile(r"^## (.+?)\s*$", flags=re.MULTILINE)
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")


def ids(path: Path) -> str:
    return path.name


def code_and_tests(path: Path) -> str:
    """最後一個 `##` 之後的內容。

    `test_feature_docs_end_with_code_and_tests` 保證它就是「程式與測試」那一段。
    """
    return H2.split(prose(path))[-1]


def test_feature_docs_are_listed_in_index() -> None:
    listed = {split(INDEX, target)[0] for target in links(INDEX)}
    unlisted = [path.name for path in FEATURES if path not in listed]
    assert not unlisted, f"docs/features/README.md 沒有列到: {unlisted}"


def test_feature_doc_filenames_are_kebab_case() -> None:
    # 不編號: 功能文件就地修改、以主題互相引用, 順序沒有意義 (ADR 才靠編號)。
    misnamed = [path.name for path in FEATURES if not FILENAME.match(path.name)]
    assert not misnamed, f"功能文件的檔名要是 kebab-case.md: {misnamed}"


@pytest.mark.parametrize("doc", FEATURES, ids=ids)
def test_feature_docs_have_a_single_title(doc: Path) -> None:
    lines = [line for line in prose(doc).splitlines() if line.strip()]
    titles = [line for line in lines if line.startswith("# ")]
    assert lines and lines[0].startswith("# "), f"{doc.name} 第一行要是 `# 標題`"
    assert len(titles) == 1, f"{doc.name} 只能有一個 `#` 標題: {titles}"


@pytest.mark.parametrize("doc", FEATURES, ids=ids)
def test_feature_docs_open_with_a_scope_paragraph(doc: Path) -> None:
    intro = H2.split(prose(doc))[0].splitlines()
    text = [line for line in intro if line.strip() and not line.startswith("#")]
    assert text, f"{doc.name} 的標題與第一個 `##` 之間要有一段說明涵蓋範圍"


@pytest.mark.parametrize("doc", FEATURES, ids=ids)
def test_feature_docs_end_with_code_and_tests(doc: Path) -> None:
    headings = H2.findall(prose(doc))
    assert headings and headings[-1] == CODE_AND_TESTS, (
        f"{doc.name} 的最後一個 `##` 要是「{CODE_AND_TESTS}」: {headings}"
    )


@pytest.mark.parametrize("doc", FEATURES, ids=ids)
def test_feature_docs_link_to_tests(doc: Path) -> None:
    section = code_and_tests(doc)
    targets = [split(doc, target)[0] for target in links(doc) if f"({target})" in section]
    tests = [path for path in targets if "tests" in path.relative_to(REPO_ROOT).parts]
    assert tests, f"{doc.name} 的「{CODE_AND_TESTS}」要至少連到一個測試檔"


@pytest.mark.parametrize("doc", FEATURES, ids=ids)
def test_feature_doc_code_paths_exist(doc: Path) -> None:
    # 連結的文字常是相對於 app 的短路徑, 只檢查連結以外、以 repo 根為準的路徑。
    # 路徑帶括號時 (`app/(protected)/…`) 不好寫成連結, 才會用行內程式碼寫。
    section = MARKDOWN_LINK.sub("", code_and_tests(doc))
    paths = [code.strip("`") for code in INLINE_CODE.findall(section) if "/" in code]
    missing = [path for path in paths if not (REPO_ROOT / path).exists()]
    assert not missing, f"{doc.name} 的「{CODE_AND_TESTS}」寫到不存在的路徑: {missing}"


@pytest.mark.parametrize("doc", FEATURES, ids=ids)
def test_feature_docs_have_no_template_comments(doc: Path) -> None:
    assert "<!--" not in doc.read_text(encoding="utf-8"), f"{doc.name} 還留著模板的註解"
