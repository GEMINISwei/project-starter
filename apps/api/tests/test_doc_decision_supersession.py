"""ADR 被推翻時, 新舊兩份與索引要一起改。

推翻一個決定要動三處: 新的 ADR 寫「取代：[NNNN](…)」, 舊的那份把狀態改成「被 [NNNN](…) 取代」,
索引的狀態欄跟著改。漏掉任何一處都不會報錯, 讀者卻會依舊的那份行事, 或在索引裡看不出它已失效。

規則寫成以目錄為參數的函式, 用暫存目錄裡的假 ADR 證明它抓得到錯, 再對真的 `docs/decisions/` 跑一次。
"""

import re
from pathlib import Path

from tests.test_doc_decisions import DECISIONS_DIR, FILENAME

STATUS_LINE = re.compile(r"^狀態：(.+?)\s*$", flags=re.MULTILINE)
SUPERSEDES_LINE = re.compile(r"^取代：(.+?)\s*$", flags=re.MULTILINE)
NUMBER_LINK = re.compile(r"\[(\d{4})\]\([^)]*\)")
INDEX_ROW = re.compile(
    r"^\|[ \t]*\[(\d{4})\]\([^)]*\)[ \t]*\|[^\n]*\|[ \t]*([^|\n]+?)[ \t]*\|[ \t]*$",
    flags=re.MULTILINE,
)
SUPERSEDED_BY = re.compile(r"^被 \[(\d{4})\]")


def read_decisions(directory: Path) -> dict[str, str]:
    return {
        match[1]: path.read_text(encoding="utf-8")
        for path in sorted(directory.glob("*.md"))
        if (match := FILENAME.match(path.name))
    }


def status(text: str) -> str:
    match = STATUS_LINE.search(text)
    return match[1] if match else ""


def supersedes(text: str) -> list[str]:
    match = SUPERSEDES_LINE.search(text)
    return NUMBER_LINK.findall(match[1]) if match else []


def plain_status(text: str) -> str:
    """索引的狀態欄寫法: 去掉日期, 連結只留編號。"""
    without_date = re.sub(r"（[^（）]*）$", "", status(text))
    return NUMBER_LINK.sub(r"\1", without_date)


def supersession_errors(directory: Path) -> list[str]:
    decisions = read_decisions(directory)
    errors = []
    for number, text in decisions.items():
        for old in supersedes(text):
            if not re.match(rf"被 \[{number}\]", status(decisions.get(old, ""))):
                errors.append(f"{number} 取代 {old}, 但 {old} 的狀態不是「被 [{number}](…) 取代」")
        replacement = SUPERSEDED_BY.match(status(text))
        if replacement and number not in supersedes(decisions.get(replacement[1], "")):
            new = replacement[1]
            errors.append(f"{number} 被 {new} 取代, 但 {new} 沒有寫「取代：[{number}](…)」")
    return errors


def index_status_errors(directory: Path) -> list[str]:
    decisions = read_decisions(directory)
    listed = dict(INDEX_ROW.findall((directory / "README.md").read_text(encoding="utf-8")))
    return [
        f"索引的 {number} 狀態是「{listed.get(number)}」, ADR 寫的是「{plain_status(text)}」"
        for number, text in decisions.items()
        if listed.get(number) != plain_status(text)
    ]


def write_decision(
    directory: Path, number: str, status_text: str, supersedes_text: str = ""
) -> None:
    extra = f"取代：{supersedes_text}\n\n" if supersedes_text else ""
    body = f"# {number}. 決定\n\n狀態：{status_text}\n\n{extra}## 背景\n\n## 決定\n\n## 後果\n"
    (directory / f"{number}-decision.md").write_text(body, encoding="utf-8")


def write_index(directory: Path, rows: dict[str, str]) -> None:
    lines = [
        f"| [{number}]({number}-decision.md) | 決定 | {text} |" for number, text in rows.items()
    ]
    (directory / "README.md").write_text(
        "| 編號 | 決定 | 狀態 |\n|---|---|---|\n" + "\n".join(lines) + "\n"
    )


# ── 對真的 docs/decisions/ ────────────────────────────────────────────────────


def test_supersessions_are_recorded_on_both_sides() -> None:
    errors = supersession_errors(DECISIONS_DIR)
    assert not errors, "\n".join(errors)


def test_index_status_matches_each_decision() -> None:
    errors = index_status_errors(DECISIONS_DIR)
    assert not errors, "\n".join(errors)


# ── 規則本身抓得到錯 ──────────────────────────────────────────────────────────


def test_supersession_check_accepts_consistent_pair(tmp_path: Path) -> None:
    write_decision(tmp_path, "0001", "被 [0002](0002-decision.md) 取代（2026-11-01）")
    write_decision(tmp_path, "0002", "採用（2026-11-01）", "[0001](0001-decision.md)")
    write_index(tmp_path, {"0001": "被 0002 取代", "0002": "採用"})

    assert supersession_errors(tmp_path) == []
    assert index_status_errors(tmp_path) == []


def test_supersession_check_catches_old_decision_still_marked_adopted(tmp_path: Path) -> None:
    write_decision(tmp_path, "0001", "採用（2026-10-25）")
    write_decision(tmp_path, "0002", "採用（2026-11-01）", "[0001](0001-decision.md)")

    assert supersession_errors(tmp_path) == [
        "0002 取代 0001, 但 0001 的狀態不是「被 [0002](…) 取代」"
    ]


def test_supersession_check_catches_replacement_without_supersedes_line(tmp_path: Path) -> None:
    write_decision(tmp_path, "0001", "被 [0002](0002-decision.md) 取代（2026-11-01）")
    write_decision(tmp_path, "0002", "採用（2026-11-01）")

    assert supersession_errors(tmp_path) == ["0001 被 0002 取代, 但 0002 沒有寫「取代：[0001](…)」"]


def test_index_check_catches_stale_status(tmp_path: Path) -> None:
    write_decision(tmp_path, "0001", "被 [0002](0002-decision.md) 取代（2026-11-01）")
    write_decision(tmp_path, "0002", "採用（2026-11-01）", "[0001](0001-decision.md)")
    write_index(tmp_path, {"0001": "採用", "0002": "採用"})

    assert index_status_errors(tmp_path) == [
        "索引的 0001 狀態是「採用」, ADR 寫的是「被 0002 取代」"
    ]
