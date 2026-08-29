"""每次請求的追蹤識別碼。

與 `errors.py` 的 `current_language` 是同一套機制（ContextVar，asyncio 每個 task 獨立），
但刻意分開放：那一個是「錯誤訊息用哪種語言」，屬於 i18n；這一個是可觀測性，
兩者會各自演進，而 `errors.py` 的 owner 是雙語文字。

用 ContextVar 而不是一路傳參數的理由同 `current_language`：需要它的是 log 與未來可能的
錯誤回報，把 request id 滲透進每一層 service 簽名，代價遠大於它的價值。
"""

import re
import secrets
from contextvars import ContextVar

# 長度上限與允許字元。**這兩個限制是必要的，不是潔癖**：這個值可能來自外部 header，
# 而它會被直接寫進 log。不限制的話，帶換行的值可以偽造出一整行假的請求紀錄
#（log injection），超長的值則能讓每一行 log 膨脹到把磁碟寫滿。
#
# nginx 的兩份設定都以 `$request_id` **覆寫**這個 header（同 X-Real-IP 的處理，
# 見 infra/nginx/templates/），所以正常路徑上的值一定是 nginx 產的。這裡的清洗守的是
# 「有人繞過 nginx 直接打 api:8000」的情況 —— 在 compose 內網裡那是做得到的。
MAX_REQUEST_ID_LENGTH = 64
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]+$")

#: 這次請求的識別碼。由 `app/server.py` 的 middleware 設定。
#: 預設值是 "-"，代表「不在請求脈絡裡」（例如 CLI 腳本或啟動流程寫的 log）。
current_request_id: ContextVar[str] = ContextVar("current_request_id", default="-")


def new_request_id() -> str:
    """產生一個新的請求識別碼。

    用 `token_hex` 而不是 uuid4：兩者都夠獨特，但 16 個字元在 log 裡短得多，
    而這個值會出現在**每一行**請求紀錄上。它不是安全憑證，只是給人跟機器對照用的標籤。
    """
    return secrets.token_hex(8)


def resolve_request_id(header_value: str | None) -> str:
    """沿用上游送來的識別碼，不合格或沒有時產生一個新的。

    沿用是 correlation 的重點：nginx、Next 伺服器端與這個 API 是三段不同的行程，
    只有共用同一個 id，一次使用者操作在三份 log 裡才串得起來。
    """
    if not header_value:
        return new_request_id()

    candidate = header_value.strip()
    if len(candidate) > MAX_REQUEST_ID_LENGTH or not _SAFE_REQUEST_ID.match(candidate):
        return new_request_id()

    return candidate
