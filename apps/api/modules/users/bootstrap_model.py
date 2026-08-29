"""系統層級的一次性狀態旗標，與使用者資料分開存放。

目前唯一的使用者是 bootstrap latch：標記「超級管理者已經建立過了」。
「最多一次」是靠 `key` 的唯一約束在併發下成立的，不是靠查詢「目前有沒有超級管理者」——
那種查法會讓兩個同時送達的 signup 都成功。

之後其他一次性旗標（維護模式、資料修復標記…）也放這裡。
"""

from typing import Any

from sqlalchemy import String, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.session import resolve_session
from shared.db.table import BaseTable

# bootstrap latch 的 key。用具名常數而不是散落的字串字面值 ——
# 打錯字的後果是「guard 永遠不會命中」，也就是 signup 悄悄地重新開放。
SUPER_ADMIN_BOOTSTRAP_KEY = "super_admin_bootstrap"


class SystemStateTable(BaseTable):
    __tablename__ = "system_state"

    key: Mapped[str] = mapped_column(String, unique=True)
    # JSONB 而不是一堆具名欄位：這裡裝的是各種一次性旗標各自的附註（bootstrap 存的是
    # 當時的 username），形狀本來就因旗標而異。要查詢裡面的內容時再開欄位。
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    @classmethod
    async def exists(cls, key: str, session: AsyncSession | None = None) -> bool:
        db = resolve_session(session)
        return await db.scalar(select(cls.id).where(cls.key == key).limit(1)) is not None
