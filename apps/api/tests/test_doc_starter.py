"""`docs/starter/`: 模板的設計決定。

子專案不改這一區, 要推翻其中一份時在 `docs/decisions/` 另寫一份並連回來
(見 `test_doc_decision_supersession.py`)。這一區因此只寫現在的決定與理由: 狀態、取代、
後續討論與日期是 ADR 累積時才需要的東西, 寫進來就分不出差異是模板改的還是子專案改的,
子專案也就沒辦法拿這一區直接跟上游比對。

段落固定而且有順序, 讀者先讀到決定與理由, 再看代價與重新檢討的時機。
連結與錨點由 `test_docs.py` 檢查。
"""

import re
from pathlib import Path

import pytest

from tests.test_doc_decisions import FILENAME
from tests.test_docs import REPO_ROOT, links, split

STARTER_DIR = REPO_ROOT / "docs" / "starter"
INDEX = STARTER_DIR / "README.md"
STARTER_DECISIONS = sorted(path for path in STARTER_DIR.glob("*.md") if FILENAME.match(path.name))
SECTIONS = ("## 決定", "## 為什麼", "## 代價", "## 什麼時候重新檢討")
HISTORY = {
    "「狀態：」": re.compile(r"^狀態：", flags=re.MULTILINE),
    "「取代：」": re.compile(r"^取代：", flags=re.MULTILINE),
    "〈後續討論〉": re.compile(r"^## 後續討論", flags=re.MULTILINE),
    "日期": re.compile(r"\b20\d{2}-\d{2}-\d{2}\b"),
}


def test_starter_decision_filenames_follow_the_numbering_format() -> None:
    misnamed = [
        path.name
        for path in STARTER_DIR.glob("*.md")
        if path != INDEX and not FILENAME.match(path.name)
    ]
    assert not misnamed, f"檔名要是 NNNN-kebab-case.md: {misnamed}"


def test_starter_decision_numbers_are_sequential() -> None:
    numbers = [int(path.name[:4]) for path in STARTER_DECISIONS]
    assert numbers, "docs/starter/ 沒有任何一份決定"
    assert numbers == list(range(1, len(numbers) + 1)), f"編號要從 0001 連續: {numbers}"


def test_starter_decisions_are_listed_in_index() -> None:
    listed = {split(INDEX, target)[0] for target in links(INDEX)}
    unlisted = [path.name for path in STARTER_DECISIONS if path not in listed]
    assert not unlisted, f"docs/starter/README.md 沒有列到: {unlisted}"


@pytest.mark.parametrize("decision", STARTER_DECISIONS, ids=lambda path: path.name)
def test_starter_decisions_have_required_sections(decision: Path) -> None:
    text = decision.read_text(encoding="utf-8")
    found = [
        match.start()
        for section in SECTIONS
        if (match := re.search(rf"^{section}\s*$", text, flags=re.MULTILINE))
    ]
    assert len(found) == len(SECTIONS), f"{decision.name} 要有這幾段: {SECTIONS}"
    assert found == sorted(found), f"{decision.name} 的段落順序要是: {SECTIONS}"


@pytest.mark.parametrize("decision", STARTER_DECISIONS, ids=lambda path: path.name)
def test_starter_decisions_have_no_status_or_history(decision: Path) -> None:
    text = decision.read_text(encoding="utf-8")
    found = [name for name, pattern in HISTORY.items() if pattern.search(text)]
    assert not found, f"{decision.name} 只寫現況, 不要有: {found}"
