from datetime import datetime
from typing import Literal, TypedDict, cast

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, select, update
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column, relationship, selectinload

from modules.roles.public import RoleTable
from shared.auth.contracts import CurrentUser
from shared.db.query import ilike_contains
from shared.db.session import resolve_session
from shared.db.table import (
    BaseTable,
    Condition,
    PagedResult,
    pagination_indexes,
    parse_uuid,
)
from shared.time import utc_now

# 使用者與角色的關聯表。
#
# 對外仍然是 `role_ids`（一個字串陣列，見 `to_detail()`），資料庫裡則是這張關聯表：
# 外鍵保證指到的角色真的存在、`role_id` 篩選變成資料庫做得到的 `EXISTS`（不必把整張
# users 撈回來過濾），角色被刪掉時也不會留下孤兒 id。
#
# 這裡刻意用 Core 的 `Table` 而不是再開一個 `BaseTable` 子類：它沒有自己的 id 與
# 時間戳，也不會有人對它做 CRUD —— 包成 model 只會讓 `app/registry.py` 多一個要註冊、
# 但沒有任何 router 或權限的東西。
user_roles = Table(
    "user_roles",
    BaseTable.metadata,
    Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "role_id",
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class UserDetail(TypedDict):
    """`find_detail_by_id` 回傳的 dict 形狀（理由見 modules/push/model.py 的同類型別）。

    與 `CurrentUser` 的差別：那一份是**認證中的自己**，由 username 查出、欄位是
    `shared/auth` 的契約；這一份是被操作的**任意使用者**，形狀比它寬（帶 `disabled_at`）。
    兩者刻意分開 —— 合成一個會讓「認證需要哪些欄位」這件事被業務欄位稀釋掉。
    """

    id: str
    username: str
    nickname: str
    role_ids: list[str]
    permissions: list[str]
    is_disabled: bool
    disabled_at: datetime | None


class UserTable(BaseTable):
    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String, unique=True)
    password: Mapped[str]
    nickname: Mapped[str]
    is_disabled: Mapped[bool] = mapped_column(default=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), default=None)
    # 每個使用者自己的 token 世代。重設密碼時 +1，讓那個人的所有既有 session 與
    # WebSocket ticket 立刻失效。
    #
    # 與 env 的 TOKEN_VERSION 不同：後者是全域撤銷，這個欄位只撤銷單一使用者的憑證。
    auth_version: Mapped[int] = mapped_column(default=1)

    # `lazy="raise"` 而不是預設的 lazy load：async session 裡的隱式 lazy load 會丟
    # `MissingGreenlet`，訊息完全看不出「你忘了 selectinload」。設成 raise 之後
    # 錯誤會直接指名這個關聯，而不是指向 greenlet。
    roles: Mapped[list[RoleTable]] = relationship(
        secondary=user_roles,
        lazy="raise",
        order_by=RoleTable.created_at,
    )

    __table_args__ = pagination_indexes("users")

    @classmethod
    def detail_loaders(cls) -> tuple[selectinload, ...]:  # type: ignore[valid-type]
        """`role_ids` 與 `permissions` 都是從 roles 算出來的，所以一律要載入關聯。

        """
        return (selectinload(cls.roles),)

    def to_detail(self) -> dict:
        """對外的使用者形狀：去掉 password，補上 `role_ids` 與展開後的 `permissions`。

        `role_ids` 列出**全部**指派到的角色，`permissions` 只聯集**未停用**角色的權限：
        停用一個角色要能立刻收回權限，但不該讓它從使用者的角色清單上消失。
        """
        data = self.to_dict()
        data.pop("password", None)
        data["role_ids"] = [str(role.id) for role in self.roles]
        data["permissions"] = sorted(
            {
                permission
                for role in self.roles
                if not role.is_disabled
                for permission in role.permissions
            }
        )
        return data

    @classmethod
    async def find_detail_by_username(
        cls,
        username: str,
        include_password: bool = False,
        session: AsyncSession | None = None,
    ) -> CurrentUser | None:
        """身分來源（`ModuleManifest.current_user_resolver`）就是這個方法。

        這裡是**整個認證路徑上唯一的型別接縫**：查詢結果在型別上是裸 dict，由這個
        `cast` 宣告成 `CurrentUser`，之後 `shared/auth` 與各 router 讀到的欄位才受
        mypy 檢查。因此改動 `to_detail()` 時要回頭確認 `CurrentUser` 列的欄位都還在
        —— cast 本身不會驗證。執行期的把關在 `GET /users/me` 的 `UserMe.model_validate()`。
        """
        db = resolve_session(session)
        statement = (
            select(cls).options(*cls.detail_loaders()).where(cls.username == username).limit(1)
        )
        row = (await db.scalars(statement)).unique().first()
        if row is None:
            return None

        data = row.to_detail()
        # password 預設不出現在 `to_detail()` 裡（那是對外形狀），登入流程要比對密碼時
        # 才明確補回來 —— 而不是反過來「預設帶著、記得要刪」。
        if include_password:
            data["password"] = row.password
        return cast(CurrentUser, data)

    @classmethod
    async def set_password_and_revoke_sessions(
        cls,
        id: str,
        password_hash: str,
        session: AsyncSession | None = None,
    ) -> dict | None:
        """換掉密碼並讓該使用者所有既有 session／WS ticket 立刻失效。

        **這兩件事必須是同一個資料庫操作。** 拆成「先改密碼、再撤銷」的話，中間任何一次
        崩潰都會留下「密碼已換、舊 session 還活著」的狀態 —— 而那正是這個功能存在的理由
        （帳號被盜時，改密碼要能把攻擊者踢下線）。

        也因此不能走 `update_by_id`：那個方法是先讀出實例、在 Python 裡比對再寫回，
        表達不了「以資料庫目前的值為基準 +1」。這裡的 `auth_version + 1` 是在
        **SQL 裡**算的，兩個併發的重設不會互相把版本號寫回舊值。
        """
        row_id = parse_uuid(id)
        if row_id is None:
            return None

        db = resolve_session(session)
        statement = (
            update(cls)
            .where(cls.id == row_id)
            .values(
                password=password_hash,
                updated_at=utc_now(),
                auth_version=cls.auth_version + 1,
            )
            .returning(cls.id)
        )
        updated_id = await db.scalar(statement)
        if updated_id is None:
            return None

        # UPDATE 是直接下到資料庫的，session 裡若已經有這個使用者的實例，它手上的
        # auth_version 就過期了。expire 掉，下次讀會重新查 —— 少了這行，同一次請求裡
        # 後續的權限檢查會拿到舊的世代值。
        db.expire_all()
        return {"id": str(updated_id)}

    @classmethod
    async def find_by_ids(
        cls,
        ids: list[str],
        session: AsyncSession | None = None,
    ) -> list[UserTable]:
        """一次取回多個使用者，供列表組裝時避免 N+1 查詢。

        會略過格式不合法的 id（而不是丟例外）：呼叫端拿到的 id 來自其他資料表的參照，
        資料若不一致應該表現為「查不到那筆」，而不是整個列表 500。
        """
        parsed = [parsed_id for id in ids if (parsed_id := parse_uuid(id))]
        if not parsed:
            return []

        statement = select(cls).options(*cls.detail_loaders()).where(cls.id.in_(parsed))
        return list((await resolve_session(session).scalars(statement)).unique().all())

    @classmethod
    def _filters(
        cls,
        name: str | None,
        role_id: str | None,
        is_disabled: bool | None,
    ) -> list[Condition]:
        filters: list[Condition] = []
        if name:
            filters.append(ilike_contains(cls.nickname, name))
        if role_id == "unassigned":
            # `~roles.any()` 展開成 `NOT EXISTS (SELECT … FROM user_roles …)`。
            filters.append(~cls.roles.any())
        elif role_id:
            parsed = parse_uuid(role_id)
            # 格式不合法的 role_id 要篩出**零筆**，不是被忽略掉而回傳全部 ——
            # 後者會讓一個打錯字的查詢看起來像是「這個角色底下有所有人」。
            filters.append(cls.roles.any(RoleTable.id == parsed) if parsed else cls.id.is_(None))
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
        role_id: str | None = None,
        is_disabled: bool | None = None,
    ) -> PagedResult:
        return await cls.get_page(
            where=cls._filters(name, role_id, is_disabled),
            cursor=cursor,
            direction=direction,
            limit=limit,
        )

    # 收窄回傳型別，理由與 `ignore[override]` 的必要性見 modules/roles/model.py 的同一處。
    @classmethod
    async def find_detail_by_id(  # type: ignore[override]
        cls, id: str, session: AsyncSession | None = None
    ) -> UserDetail | None:
        return cast(UserDetail | None, await super().find_detail_by_id(id, session))

    # ── role_ids 的寫入路徑 ───────────────────────────────────────────────────
    #
    # `role_ids` 對外仍然是一個字串陣列（API 契約沒有變），但它在資料庫裡已經是
    # user_roles 這張關聯表。下面兩個覆寫就是那道轉換：service 層完全不知道有關聯表。

    @staticmethod
    async def _load_roles(db: AsyncSession, role_ids: list[str]) -> list[RoleTable]:
        parsed = [parsed_id for role_id in role_ids if (parsed_id := parse_uuid(role_id))]
        if not parsed:
            return []
        rows = (await db.scalars(select(RoleTable).where(RoleTable.id.in_(parsed)))).all()
        # 依傳入順序排回來，讓 `role_ids` 的往返保持穩定（IN 查詢不保證順序）。
        by_id = {row.id: row for row in rows}
        return [by_id[parsed_id] for parsed_id in parsed if parsed_id in by_id]

    @classmethod
    async def create(cls, data: dict, session: AsyncSession | None = None) -> dict:
        payload = dict(data)  # 不要改到呼叫端的 dict
        role_ids = payload.pop("role_ids", None) or []
        db = resolve_session(session)

        row = cls(**cls._coerce(payload))
        row.roles = await cls._load_roles(db, role_ids)
        db.add(row)
        await db.flush()
        return row.to_dict()

    @classmethod
    async def update_by_id(
        cls,
        id: str,
        data: dict | None = None,
        session: AsyncSession | None = None,
        *,
        also_changed: bool = False,
    ) -> dict | None:
        """與基底相同的「只寫真的有變的欄位」語義，另外把 `role_ids` 轉成關聯。

        角色的比對用**集合**：`{a, b}` 與 `{b, a}` 是同一組指派，若比對順序，前端把
        多選框的順序換一下就會被當成一次更新（而它其實什麼都沒改）。
        """
        payload = dict(data or {})
        has_roles = "role_ids" in payload
        role_ids = payload.pop("role_ids", None) or []
        db = resolve_session(session)

        row_id = parse_uuid(id)
        if row_id is None:
            return None
        statement = select(cls).options(*cls.detail_loaders()).where(cls.id == row_id).limit(1)
        row = (await db.scalars(statement)).unique().first()
        if row is None:
            return None

        roles_changed = False
        if has_roles:
            wanted = await cls._load_roles(db, role_ids)
            roles_changed = {role.id for role in wanted} != {role.id for role in row.roles}

        # 欄位的比對交給基底，避免兩套「怎麼算有變」的規則。`also_changed` 告訴它
        # 「角色改了」也算一次更新，否則欄位剛好都沒變時會被判成 204 而把角色的異動丟掉。
        result = await super().update_by_id(
            id, payload, session=db, also_changed=also_changed or roles_changed
        )

        if roles_changed:
            row.roles = wanted
            await db.flush()

        return result
