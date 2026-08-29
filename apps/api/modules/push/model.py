import uuid
from typing import TypedDict, cast

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.table import BaseTable, parse_uuid


class PushSubscriptionDetail(TypedDict):
    """`find_*_detail*` 回傳的 dict 形狀。

    只列**呼叫端真的會讀**的欄位，不是資料表的完整形狀 —— 這份型別是給
    `service.py` 與 `dispatcher.py` 用的契約，不是資料表定義（那個在下面的 model）。

    標成 TypedDict 的理由同 `shared/auth/contracts.py` 的 `CurrentUser`：
    查詢結果在型別上是裸 dict，`subscription["p256dh"]` 這種存取完全不受
    mypy 檢查，改一個欄位名要到執行期才變成 `KeyError` → 推播整批失敗。
    """

    id: str
    user_id: str
    endpoint: str
    p256dh: str
    auth: str


class PushSubscriptionTable(BaseTable):
    __tablename__ = "push_subscriptions"

    # `ON DELETE CASCADE`：使用者被刪掉時他的訂閱一起消失。留著只會讓廣播對著
    # 一批永遠推不到的 endpoint 重試。
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
    )
    endpoint: Mapped[str] = mapped_column(String, unique=True)
    p256dh: Mapped[str]
    auth: Mapped[str]
    user_agent: Mapped[str | None] = mapped_column(default=None)

    __table_args__ = (Index("ix_push_subscriptions_user_id", "user_id"),)

    # 底下三個 `cast` 是這個模組**唯一**的型別接縫：查詢的輸出在型別上是裸 dict，
    # 由這裡宣告成 `PushSubscriptionDetail`，之後 service 與 dispatcher 讀欄位才受檢查。
    # cast 本身不做執行期驗證，所以改動 `to_detail()` 時要回頭確認欄位還在 ——
    # `tests/shared/test_detail_lookup.py` 有一條測試跑真正的查詢在守這件事。

    @classmethod
    async def find_detail_by_endpoint(
        cls,
        endpoint: str,
        session: AsyncSession | None = None,
    ) -> PushSubscriptionDetail | None:
        result = await cls.find_detail_one(cls.endpoint == endpoint, session=session)
        return cast(PushSubscriptionDetail | None, result)

    @classmethod
    async def find_details_by_user_id(
        cls,
        user_id: str,
        session: AsyncSession | None = None,
    ) -> list[PushSubscriptionDetail]:
        parsed = parse_uuid(user_id)
        if parsed is None:
            return []
        result = await cls.get_all(where=[cls.user_id == parsed], session=session)
        return cast(list[PushSubscriptionDetail], result["list_data"])

    @classmethod
    async def find_all_details(
        cls,
        session: AsyncSession | None = None,
    ) -> list[PushSubscriptionDetail]:
        result = await cls.get_all(session=session)
        return cast(list[PushSubscriptionDetail], result["list_data"])
