"""釘住「寫進資料庫的時間戳一律是 naive UTC」這個不變量。"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime

from app.registry import TABLE_MODELS
from shared.time import expires_at, utc_now


def test_utc_now_is_naive():
    assert utc_now().tzinfo is None


def test_utc_now_matches_utc_wall_clock():
    assert abs(utc_now() - datetime.now(UTC).replace(tzinfo=None)) < timedelta(seconds=5)


# `BaseTable` 本身沒有 `__table__`（它是宣告用的基底，不對應任何資料表），
# 所以下面兩條走真正註冊的 model —— 它們繼承的正是要驗的那份欄位定義。


def test_created_at_defaults_to_utc_now():
    """避免有人把預設值換回 `datetime.now`（本地時間）或資料庫的 `now()`（帶時區）。"""
    for model in TABLE_MODELS:
        default = model.__table__.columns["created_at"].default
        assert default is not None, model.__name__
        # SQLAlchemy 會把零參數的 callable 包一層（讓它收得到 execution context），
        # 原本那個掛在 `__wrapped__` 上 —— 比對包裝後的物件永遠不會相等。
        assert getattr(default.arg, "__wrapped__", default.arg) is utc_now, model.__name__


def test_timestamps_are_stored_without_timezone():
    """欄位型別必須是 `TIMESTAMP WITHOUT TIME ZONE`。

    帶時區的話，asyncpg 讀回來的是 aware datetime，而全專案其他地方算出來的是 naive
    （見 `utc_now`）—— 兩者相減直接 TypeError，而且只在真的碰資料庫時才會發生。
    """
    for model in TABLE_MODELS:
        for column in ("created_at", "updated_at"):
            column_type = model.__table__.columns[column].type
            assert isinstance(column_type, DateTime), model.__name__
            assert column_type.timezone is False, model.__name__


def test_expires_at_is_timezone_aware():
    """JWT 的 exp 必須帶時區。

    naive datetime 會被 python-jose 當成本地時間轉 epoch，在非 UTC 時區的機器上
    簽出的 token 有效期會整個偏掉（偏移量正好是機器的 UTC offset）。
    """
    assert expires_at(hours=1).tzinfo is not None


def test_expires_at_offsets_from_now():
    """釘住「相對於現在的長度」而非絕對值。"""
    tolerance = timedelta(seconds=5)
    assert abs((expires_at(hours=3) - datetime.now(UTC)) - timedelta(hours=3)) < tolerance
    assert abs((expires_at(seconds=60) - datetime.now(UTC)) - timedelta(seconds=60)) < tolerance


def test_expires_at_defaults_to_now():
    assert abs(expires_at() - datetime.now(UTC)) < timedelta(seconds=5)
