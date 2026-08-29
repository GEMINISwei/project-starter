from datetime import datetime
from typing import Literal, TypedDict, cast

from sqlalchemy import ARRAY, DateTime, String
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.permissions import Permission
from shared.db.query import ilike_contains
from shared.db.table import (
    BaseTable,
    Condition,
    PagedResult,
    SimpleListResult,
    pagination_indexes,
    parse_uuid,
)

SUPER_ADMIN_ROLE_CODE = "super_admin"


class RoleDetail(TypedDict):
    """`find_detail_*` 回傳的 dict 形狀（理由見 modules/push/model.py 的同類型別）。

    `code` 的值可以是 `None`（非系統角色），但**鍵一定在**，所以是 `str | None` 而不是
    `NotRequired`。這個差別有實際後果：宣告成必填之後，呼叫端才能寫 `role["code"]` 而不是
    `role.get("code")` —— 而 mypy 對 TypedDict 的 `.get()` 用未知鍵時只回傳 `object`，
    **不會報錯**，等於打錯字又溜回執行期。這份型別裡的欄位一律用 `[...]` 存取。
    """

    id: str
    code: str | None
    name: str
    permissions: list[Permission]
    is_disabled: bool
    disabled_at: datetime | None


class RoleTable(BaseTable):
    __tablename__ = "roles"

    # UNIQUE 但可以是 NULL：PostgreSQL 的唯一約束不把多個 NULL 視為重複，所以一般角色
    # （`code = NULL`）要幾個有幾個，只有系統角色的 code 不能撞號。
    code: Mapped[str | None] = mapped_column(String, unique=True, default=None)
    name: Mapped[str]
    # 用 `text[]` 而不是 JSONB：權限是一維字串集合，陣列型別能保留順序（roles service
    # 會直接比對 `role["permissions"] != form_data.permissions`），也留著日後加 GIN 索引
    # 做「哪些角色有這個權限」查詢的路。
    permissions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    is_disabled: Mapped[bool] = mapped_column(default=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), default=None)

    __table_args__ = pagination_indexes("roles")

    seed_match_key = "code"
    seed_data = [
        {
            "code": SUPER_ADMIN_ROLE_CODE,
            "name": "超級管理者",
            "permissions": [Permission.ALL],
            "is_disabled": False,
            "disabled_at": None,
        },
    ]

    @classmethod
    async def find_details_by_ids(
        cls,
        role_ids: list[str],
        session: AsyncSession | None = None,
    ) -> list[RoleDetail]:
        parsed = [parsed_id for role_id in role_ids if (parsed_id := parse_uuid(role_id))]
        if not parsed:
            return []

        result = await cls.get_all(where=[cls.id.in_(parsed)], session=session)
        return cast(list[RoleDetail], result["list_data"])

    # 角色沒有要補的關聯資料，所以不覆寫 `detail_loaders()` ——
    # `find_detail_by_id` 直接用 `BaseTable` 的實作即可。

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
            where=cls._filters(name, is_disabled),
            cursor=cursor,
            direction=direction,
            limit=limit,
        )

    @classmethod
    async def find_options(cls, is_disabled: bool | None = None) -> SimpleListResult:
        """非分頁的完整角色清單，供前端填下拉選單使用。

        角色數量由管理者手動建立，天然有限，所以這裡完整回傳。非分頁選項與分頁列表由
        不同端點提供，讓各自的回應形狀保持明確。
        """
        return await cls.get_all(where=cls._filters(None, is_disabled))

    @classmethod
    def is_system_role(cls, role: RoleDetail) -> bool:
        return role["code"] is not None

    @classmethod
    async def find_detail_by_code(
        cls,
        code: str,
        session: AsyncSession | None = None,
    ) -> RoleDetail | None:
        result = await cls.find_detail_one(cls.code == code, session=session)
        return cast(RoleDetail | None, result)

    # 覆寫只為了收窄回傳型別 —— 基底的 `find_detail_by_id` 回傳裸 dict，呼叫端讀欄位
    # 就完全不受檢查。實作仍然是基底那一份（角色沒有要補的關聯資料）。
    #
    # `ignore[override]` 是必要的，不是偷懶：TypedDict 在名義上不是 `dict[Any, Any]` 的
    # 子型別，所以 mypy 把「回傳型別變窄」也判成不相容 —— 但收窄回傳值對呼叫端只會更安全。
    @classmethod
    async def find_detail_by_id(  # type: ignore[override]
        cls, id: str, session: AsyncSession | None = None
    ) -> RoleDetail | None:
        return cast(RoleDetail | None, await super().find_detail_by_id(id, session))

    @classmethod
    async def get_super_admin_role_id(cls) -> str:
        return await cls.get_system_role_id(SUPER_ADMIN_ROLE_CODE)

    @classmethod
    async def get_system_role_id(cls, code: str) -> str:
        role = await cls.find_detail_by_code(code)
        if role is None:
            await cls.ensure_seed()
            role = await cls.find_detail_by_code(code)
        if role is None:
            raise RuntimeError(f"system role not found: {code}")
        return role["id"]
