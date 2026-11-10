"""api 自己寫的 log (請求紀錄、AUDIT) 共用的輸出格式。

跟 uvicorn 預設 log 一樣的 `LEVEL:` 對齊寫法, 時間用 [] 包住。各自一個 logger 而不是共用:
`grep AUDIT` 與請求紀錄是兩種用途, 測試也要能分開收。
"""

import logging
import time


class _LineFormatter(logging.Formatter):
    """時間一律 UTC 並標出 `Z`: 容器、主機與看 log 的人時區可能都不同, 沒標時區的時間很容易差
    8 小時而不自知。
    """

    converter = staticmethod(time.gmtime)

    def formatMessage(self, record: logging.LogRecord) -> str:  # noqa: N802 # 覆寫標準庫的方法名
        separator = " " * (8 - len(record.levelname))
        levelprefix = f"{record.levelname}:{separator}"
        timestamp = self.formatTime(record, self.datefmt)
        return f"{levelprefix}[{timestamp}] {record.message}"


def stream_logger(name: str) -> logging.Logger:
    """寫到 stdout/stderr 的 INFO 等級 logger, 不往 root 傳 (root 的設定由 uvicorn 決定)。"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_LineFormatter(datefmt="%Y-%m-%dT%H:%M:%SZ"))
        logger.addHandler(handler)
        logger.propagate = False
    return logger
