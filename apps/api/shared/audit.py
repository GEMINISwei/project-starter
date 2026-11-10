"""安全事件的紀錄: 一個事件一行, 固定以 `AUDIT` 開頭, `grep AUDIT` 就挑得出來。

一般的請求紀錄看得到「誰打了哪條路徑、回了什麼狀態碼」, 看不到「登入失敗的原因」「改了誰的角色」;
事後調查 (帳號被盜、權限設錯) 要的是這些。每一筆自動帶上 request id、操作者 (`actor`) 與 IP,
呼叫端只給事件自己的欄位。

**只放 id 與固定的代碼**, 不放帳號、暱稱或使用者輸入的內容: log 會長期留存、會被備份與轉送。
"""

import json
import re
from collections.abc import Iterable

from shared.http.context import current_client_ip, current_request_id, current_user_id
from shared.logs import stream_logger

audit_logger = stream_logger("api.audit")

# 不必加引號的值。其他的 (空白、換行、引號等) 以 JSON 字串寫出: 換行會被跳脫,
# 一筆紀錄偽造不出另一行。
_PLAIN_VALUE = re.compile(r"^[A-Za-z0-9._:/@*,+-]+$")


def _format_value(value: object) -> str:
    if isinstance(value, Iterable) and not isinstance(value, str):
        value = ",".join(str(item) for item in value) or "-"
    text = str(value)
    return text if _PLAIN_VALUE.match(text) else json.dumps(text, ensure_ascii=False)


def audit(event: str, **fields: object) -> None:
    """記一筆安全事件。值是 None 的欄位不寫; 清單寫成逗號分隔, 空清單寫 `-`。"""
    parts = [
        f"AUDIT [{current_request_id.get()}] {event}",
        f"actor={_format_value(current_user_id.get())}",
        f"ip={current_client_ip.get()}",
        *(f"{key}={_format_value(value)}" for key, value in fields.items() if value is not None),
    ]
    audit_logger.info(" ".join(parts))
