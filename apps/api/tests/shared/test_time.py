"""釘住「寫進資料庫的時間戳一律是 naive UTC」這個不變量, 以及它送出去時的形狀。

兩半要一起看: 存進去是 naive (沒有時區資訊), 送出去**必須**補上 `Z`, 否則收到的人
沒有任何辦法知道那是哪個時區的時間。後半由 `shared/http/schema.UtcDateTime` 負責。
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel
from sqlalchemy import DateTime

from shared.db.table import BaseTable
from shared.http.schema import UtcDateTime
from shared.time import expires_at, utc_now


def test_utc_now_is_naive():
    assert utc_now().tzinfo is None


def test_utc_now_matches_utc_wall_clock():
    assert abs(utc_now() - datetime.now(UTC).replace(tzinfo=None)) < timedelta(seconds=5)


class _StampRow(BaseTable):
    """`BaseTable` 本身沒有 `__table__` (它是宣告用的基底), 用一張只存在於測試裡的表驗它
    宣告的時間欄位。已註冊的 model 有沒有把它改掉, 由 `tests/app/test_registry.py` 檢查。"""

    __tablename__ = "test_stamp_rows"


def test_created_at_defaults_to_utc_now():
    """避免有人把預設值換回 `datetime.now` (本地時間) 或資料庫的 `now()` (帶時區)。"""
    default = _StampRow.__table__.columns["created_at"].default
    assert default is not None
    # SQLAlchemy 會把零參數的 callable 包一層 (讓它收得到 execution context),
    # 原本那個掛在 `__wrapped__` 上 —— 比對包裝後的物件永遠不會相等。
    assert getattr(default.arg, "__wrapped__", default.arg) is utc_now


def test_timestamps_are_stored_without_timezone():
    """欄位型別必須是 `TIMESTAMP WITHOUT TIME ZONE`。

    帶時區的話, asyncpg 讀回來的是 aware datetime, 而全專案其他地方算出來的是 naive
    (見 `utc_now`) —— 兩者相減直接 TypeError, 而且只在真的碰資料庫時才會發生。
    """
    for column in ("created_at", "updated_at"):
        column_type = _StampRow.__table__.columns[column].type
        assert isinstance(column_type, DateTime)
        assert column_type.timezone is False


def test_expires_at_is_timezone_aware():
    """JWT 的 exp 必須帶時區。

    naive datetime 會被 PyJWT 當成本地時間轉 epoch, 在非 UTC 時區的機器上
    簽出的 token 有效期會整個偏掉 (偏移量正好是機器的 UTC offset)。
    """
    assert expires_at(hours=1).tzinfo is not None


def test_expires_at_offsets_from_now():
    """釘住「相對於現在的長度」而非絕對值。"""
    tolerance = timedelta(seconds=5)
    assert abs((expires_at(hours=3) - datetime.now(UTC)) - timedelta(hours=3)) < tolerance
    assert abs((expires_at(seconds=60) - datetime.now(UTC)) - timedelta(seconds=60)) < tolerance


# ── 送出去的那一半: UtcDateTime ───────────────────────────────────────────────


class _Sample(BaseModel):
    at: UtcDateTime


def test_utc_datetime_marks_naive_values_as_utc():
    """naive 值 (資料庫來的那種) 要補上 `Z`, 牆上時間不變。"""
    dumped = _Sample(at=datetime(2026, 9, 3, 0, 36, 56)).model_dump(mode="json")
    assert dumped["at"] == "2026-09-03T00:36:56Z"


def test_utc_datetime_converts_aware_values():
    """aware 值要換算成 UTC, 而不是把原本的 offset 原樣送出。

    兩種形狀混在同一個欄位上時, 前端只會在其中一種上出錯 —— 而那種錯不會有例外,
    只是時間不對。
    """
    taipei = datetime(2026, 9, 3, 8, 36, 56, tzinfo=timezone(timedelta(hours=8)))
    assert _Sample(at=taipei).model_dump(mode="json")["at"] == "2026-09-03T00:36:56Z"


def test_utc_datetime_keeps_datetime_in_python_mode():
    """`model_dump()` (python 模式) 仍然是 datetime —— 序列化只發生在出去的那一刻。

    後端內部互相傳遞時還要能拿它做運算, 轉成字串會讓呼叫端得自己再 parse 回來。
    """
    assert _Sample(at=datetime(2026, 9, 3)).model_dump()["at"] == datetime(2026, 9, 3)


@pytest.mark.asyncio
async def test_utc_datetime_survives_the_fastapi_response_path():
    """**這條才是真正要守的**: FastAPI 實際回給瀏覽器的 body 裡有沒有那個 `Z`。

    上面幾條驗的是 pydantic 的行為, 但回應是經過 FastAPI 的 response_model 序列化出去
    的 —— 那條路徑換了模式 (例如某次升級改成先 python 模式再自己編碼), `Z` 就會安靜地
    消失, 而上面那幾條照樣綠。所以這裡打一次真的請求。
    """
    app = FastAPI()

    @app.get("/sample")
    async def sample() -> _Sample:
        return _Sample(at=datetime(2026, 9, 3, 0, 36, 56, 638068))

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/sample")

    assert response.json()["at"].endswith("Z")

    schema = app.openapi()["components"]["schemas"]["_Sample"]["properties"]["at"]
    # 契約上仍然要看得出這是時間。PlainSerializer 預設會讓它變成裸的 string,
    # `WithJsonSchema` 就是為了補回這件事 —— 沒有這條斷言, 那一行被刪掉不會有症狀。
    assert schema == {"type": "string", "format": "date-time", "title": "At"}
