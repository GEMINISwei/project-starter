"""時間處理：提供資料庫時間戳與 JWT 到期時間所需的兩個函式。"""

from datetime import UTC, datetime, timedelta


def utc_now() -> datetime:
    """**所有要寫進資料庫的時間戳一律用這個**：naive UTC。

    所有時間欄位的型別都是 `TIMESTAMP WITHOUT TIME ZONE`（見 `shared/db/table.py`），
    讀回來就是 naive；寫入時保持一致，跨欄位比較才不會悄悄算錯（例如拿本地時區的
    `created_at` 去比對 UTC 的週起點），也不會出現 aware 與 naive 相減直接 TypeError。

    需要「帶時區、要離開系統」的時間（例如 JWT `exp`）才用下面的 `expires_at`。
    """
    return datetime.now(UTC).replace(tzinfo=None)


def expires_at(*, hours: int = 0, seconds: int = 0) -> datetime:
    """從現在起算的到期時間，**帶 UTC 時區**。

    給要離開系統的時間欄位使用 —— 目前是 JWT 的 `exp`。回傳 aware datetime 是刻意的：
    JWT 函式庫會呼叫 `utctimetuple()` 把它轉成 epoch，naive datetime 會被當成本地時間，
    在非 UTC 時區的機器上簽出的 token 有效期會整個偏掉。
    """
    return datetime.now(UTC) + timedelta(hours=hours, seconds=seconds)
