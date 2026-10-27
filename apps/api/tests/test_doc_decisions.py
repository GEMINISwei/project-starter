"""`docs/decisions/` (ADR) 的編號、索引與段落。

ADR 只累積不合併, 用編號互相引用: 編號跳號或重複時, 「被 0007 取代」這類連結就指錯對象。
沒列進索引的 ADR 不會被讀到, 同一個問題就會被重新提出。段落固定, 讀者才能直接跳到「決定」。

連結與錨點由 `test_docs.py` 檢查, 這裡只管 ADR 自己的規則。
"""

import re
from pathlib import Path

import pytest

from tests.test_docs import REPO_ROOT, links, split

DECISIONS_DIR = REPO_ROOT / "docs" / "decisions"
INDEX = DECISIONS_DIR / "README.md"
FILENAME = re.compile(r"^(\d{4})-[a-z0-9]+(-[a-z0-9]+)*\.md$")
DECISIONS = sorted(path for path in DECISIONS_DIR.glob("*.md") if FILENAME.match(path.name))
SECTIONS = ("## 背景", "## 決定", "## 後果")
STATUS = re.compile(r"^狀態：\S", flags=re.MULTILINE)


def test_decision_filenames_follow_the_numbering_format() -> None:
    others = {INDEX.name, "_template.md"}
    misnamed = [
        path.name
        for path in DECISIONS_DIR.glob("*.md")
        if path.name not in others and not FILENAME.match(path.name)
    ]
    assert not misnamed, f"ADR 檔名要是 NNNN-kebab-case.md: {misnamed}"


def test_decision_numbers_are_sequential() -> None:
    # DECISIONS 已經用 FILENAME 篩過, 前四碼一定是編號。
    numbers = [int(path.name[:4]) for path in DECISIONS]
    assert numbers == list(range(1, len(numbers) + 1)), f"ADR 編號要從 0001 連續: {numbers}"


def test_decisions_are_listed_in_index() -> None:
    listed = {split(INDEX, target)[0] for target in links(INDEX)}
    unlisted = [path.name for path in DECISIONS if path not in listed]
    assert not unlisted, f"docs/decisions/README.md 沒有列到: {unlisted}"


@pytest.mark.parametrize("decision", DECISIONS, ids=lambda path: path.name)
def test_decisions_have_status_and_required_sections(decision: Path) -> None:
    text = decision.read_text(encoding="utf-8")
    missing = [section for section in SECTIONS if not re.search(rf"^{section}\s*$", text, re.M)]
    assert STATUS.search(text), f"{decision.name} 缺少「狀態：」那一行"
    assert not missing, f"{decision.name} 缺少段落: {missing}"
