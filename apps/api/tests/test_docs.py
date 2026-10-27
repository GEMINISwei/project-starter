"""文件之間的連結與 `docs/features/` 的索引。

文件拆檔或改標題時, 指向它的連結會安靜地失效: Markdown 不會報錯, 讀者 (尤其是照連結找文件的
AI agent) 只會找不到內容。錨點用 GitHub 的規則從標題產生, 改一個字就對不上。

`docs/features/` 會隨功能增加, AI 靠索引那一行判斷要不要讀哪一份, 沒列進索引的文件等於不存在。

住在 api 底下的理由同 `test_nginx_templates.py`: `make check` 一定會跑到這裡。
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FEATURES_DIR = REPO_ROOT / "docs" / "features"
DOCS = sorted(
    [
        *REPO_ROOT.glob("*.md"),
        *(REPO_ROOT / "docs").rglob("*.md"),
        *(REPO_ROOT / ".github").rglob("*.md"),
    ]
)

FENCE = re.compile(r"^(```|~~~).*?^\1", flags=re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r"`[^`\n]*`")
LINK = re.compile(r"\]\(([^)\s]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$", flags=re.MULTILINE)
EXTERNAL = ("http://", "https://", "mailto:")


def prose(path: Path) -> str:
    """去掉程式碼區塊, 裡面的 `](…)` 不是連結。"""
    return FENCE.sub("", path.read_text(encoding="utf-8"))


def links(path: Path) -> list[str]:
    return [
        target
        for target in LINK.findall(INLINE_CODE.sub("", prose(path)))
        if not target.startswith(EXTERNAL)
    ]


def slug(heading: str) -> str:
    """GitHub 的錨點規則: 去掉行內標記與標點, 轉小寫, 空白換成 `-`。"""
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading).replace("`", "")
    return re.sub(r"[^\w\- ]", "", text.lower()).replace(" ", "-")


def anchors(path: Path) -> set[str]:
    """同名標題由 GitHub 依序加上 `-1`、`-2`。"""
    seen: dict[str, int] = {}
    result = set()
    for heading in HEADING.findall(prose(path)):
        base = slug(heading)
        count = seen.get(base, 0)
        seen[base] = count + 1
        result.add(base if count == 0 else f"{base}-{count}")
    return result


def split(source: Path, target: str) -> tuple[Path, str]:
    file_part, _, anchor = target.partition("#")
    return (source.parent / file_part).resolve() if file_part else source, anchor


@pytest.mark.parametrize("doc", DOCS, ids=lambda path: str(path.relative_to(REPO_ROOT)))
def test_relative_links_point_to_existing_files(doc: Path) -> None:
    missing = [target for target in links(doc) if not split(doc, target)[0].exists()]
    assert not missing, f"{doc.relative_to(REPO_ROOT)} 連到不存在的路徑: {missing}"


@pytest.mark.parametrize("doc", DOCS, ids=lambda path: str(path.relative_to(REPO_ROOT)))
def test_link_anchors_match_headings(doc: Path) -> None:
    broken = []
    for target in links(doc):
        path, anchor = split(doc, target)
        if anchor and path.suffix == ".md" and path.exists() and anchor not in anchors(path):
            broken.append(target)
    assert not broken, f"{doc.relative_to(REPO_ROOT)} 的錨點對不上標題: {broken}"


def test_feature_docs_are_listed_in_index() -> None:
    index = FEATURES_DIR / "README.md"
    listed = {split(index, target)[0] for target in links(index)}
    unlisted = [
        path.name
        for path in sorted(FEATURES_DIR.glob("*.md"))
        if path != index and path not in listed
    ]
    assert not unlisted, f"docs/features/README.md 沒有列到: {unlisted}"
