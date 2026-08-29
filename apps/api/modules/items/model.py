"""**範例模組** —— 一個最小但完整的資料模型，示範這個模板的擴充方式。

它刻意不代表任何真實業務（就叫「項目」），存在的理由是讓「新增一個模組要怎麼寫」
有一份可以照抄的實作，而不是只有文件。用不到時可以整包刪除，見 docs/architecture.md「移除 module」。

這裡示範的機制：

- `pagination_indexes()`：游標分頁需要的標準索引組合
- `find_list` 的 `where`：**會影響筆數**的條件（名稱、狀態），因此 `total_count` 才會正確
- `detail_loaders()` + `to_detail()`：**不影響筆數**的補充（撈建立者暱稱），
  `selectinload` 只會對最終要回傳的那幾筆另發一次查詢，不會隨候選資料量變貴

兩者的分工是 `BaseTable.get_page` 的核心設計，詳見該方法的 docstring。
"""

import uuid
from datetime import datetime
from typing import Literal, TypedDict, cast

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from modules.users.public import UserTable
from shared.db.query import ilike_contains
from shared.db.table import (
    BaseTable,
    Condition,
    PagedResult,
    pagination_indexes,
)


class ItemDetail(TypedDict):
    """`find_detail_by_id` 與 `create` 回傳的 dict 形狀（理由見 modules/push/model.py）。"""

    id: str
    name: str
    description: str
    is_disabled: bool
    disabled_at: datetime | None
    created_by_id: str | None


class ItemTable(BaseTable):
    __tablename__ = "items"

    name: Mapped[str]
    description: Mapped[str] = mapped_column(default="")
    is_disabled: Mapped[bool] = mapped_column(default=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), default=None)
    # 外鍵而不是裸字串：指到不存在的使用者會在寫入當下失敗，而不是等到列表查詢時
    # 靜靜地顯示成空的建立者。
    # `ON DELETE SET NULL` —— 使用者被硬刪時項目要留著，只是不再知道是誰建的。
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        default=None,
    )
    created_by: Mapped[UserTable | None] = relationship(lazy="raise")

    __table_args__ = pagination_indexes("items")

    @classmethod
    def detail_loaders(cls) -> tuple[selectinload, ...]:  # type: ignore[valid-type]
        """取單筆與列表時一併載入建立者，供 `to_detail()` 取暱稱。

        """
        return (selectinload(cls.created_by),)

    def to_detail(self) -> dict:
        """補上 `created_by_nickname`，找不到建立者時留空字串。"""
        data = self.to_dict()
        data["created_by_nickname"] = self.created_by.nickname if self.created_by else ""
        return data

    # 收窄回傳型別，理由與 `ignore[override]` 的必要性見 modules/roles/model.py 的同一處。
    @classmethod
    async def find_detail_by_id(  # type: ignore[override]
        cls, id: str, session: AsyncSession | None = None
    ) -> ItemDetail | None:
        return cast(ItemDetail | None, await super().find_detail_by_id(id, session))

    @classmethod
    async def create(  # type: ignore[override]
        cls, data: dict, session: AsyncSession | None = None
    ) -> ItemDetail:
        return cast(ItemDetail, await super().create(data, session))

    @classmethod
    def _filters(cls, name: str | None, is_disabled: bool | None) -> list[Condition]:
        filters: list[Condition] = []
        if name:
            filters.append(ilike_contains(cls.name, name))
        if is_disabled is not None:
            filters.append(cls.is_disabled.is_(is_disabled))

        return filters

    @classmethod
    async def find_list(
        cls,
        limit: int,
        cursor: str | None = None,
        direction: Literal["next", "prev"] = "next",
        name: str | None = None,
        is_disabled: bool | None = None,
    ) -> PagedResult:
        return await cls.get_page(
            # 篩選放 `where`：它會影響「符合條件的總筆數」。
            # 補建立者暱稱不放這裡 —— 那是 `detail_loaders()` 的事，不影響筆數。
            where=cls._filters(name, is_disabled),
            cursor=cursor,
            direction=direction,
            limit=limit,
        )
