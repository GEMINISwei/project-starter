"""AUDIT 紀錄 (`shared/audit.py`) 的測試輔助: 把收到的紀錄拆成 (事件, 欄位), 以及設定操作者。

拆解靠 `shlex`: 值帶空白或換行時會以雙引號包住並跳脫 (見 `test_audit.py`), 一般值不加引號。
"""

import contextlib
import logging
import shlex
from collections.abc import Iterator

from shared.http.context import current_user_id


def parse(message: str) -> tuple[str, dict[str, str]]:
    """`AUDIT [request id] 事件 k=v ...` → (事件, {"request_id": ..., k: v})。"""
    parts = shlex.split(message)
    assert parts[0] == "AUDIT", message
    fields = dict(part.split("=", 1) for part in parts[3:])
    return parts[2], {"request_id": parts[1].strip("[]"), **fields}


def events(records: list[logging.LogRecord]) -> list[tuple[str, dict[str, str]]]:
    return [parse(record.getMessage()) for record in records]


@contextlib.contextmanager
def acting_as(user_id: str) -> Iterator[None]:
    """模擬「這個請求的操作者是 user_id」: 正式路徑上由權限檢查的 dependency 設定。"""
    token = current_user_id.set(user_id)
    try:
        yield
    finally:
        current_user_id.reset(token)
