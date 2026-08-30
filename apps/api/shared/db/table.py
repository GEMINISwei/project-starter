"""所有資料表的共同基底：欄位慣例、CRUD、游標分頁與 seed。

兩個貫穿整層的分工，動手改之前先讀懂：

- **`where` 會影響筆數，`detail_loaders()` 不會。** 前者同時套用在資料查詢與
  `total_count` 的 `COUNT(*)` 上；後者只是替已經取回的那幾列補關聯資料，用
  `selectinload` 另發一次 `WHERE id IN (...)`，成本不隨候選筆數成長。
  兩者混在一起的後果是 `total_count` 算錯，而列表看起來完全正常。
- **對外的 id 一律是字串，資料庫裡是 UUID。** `to_dict()` 負責出去那一段的轉換，
  `_coerce()` 負責進來那一段。中間層（service、router）從頭到尾只看得到字串。
"""

import base64
import json
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, ClassVar, Literal, NotRequired, Self, TypedDict

from sqlalchemy import DateTime, Index, Select, and_, desc, func, inspect, or_, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql.base import ExecutableOption
from sqlalchemy.sql.elements import ColumnElement

from shared.db.session import resolve_session
from shared.http.errors import BaseError, LangException, LangText, NoChangeError
from shared.time import utc_now

Condition = ColumnElement[bool]


class SimpleListResult(TypedDict):
    """`get_all` 的回傳形狀，對應 `shared/http/schema.SimpleListResponse[T]`。"""

    list_data: list[dict]
    count: int


class PagedResult(TypedDict):
    """`get_page` 的回傳形狀，對應 `shared/http/schema.PaginatedResponse[T]`。"""

    list_data: list[dict]
    next_cursor: NotRequired[str | None]
    prev_cursor: NotRequired[str | None]
    has_next: bool
    has_previous: bool
    total_count: int


class PaginationError(BaseError):
    INVALID_CURSOR = LangText(zh="分頁游標無效", en="Invalid Pagination Cursor")


def is_unique_violation(error: Exception) -> bool:
    """這個 `IntegrityError` 是不是撞到唯一約束（而不是外鍵、NOT NULL 之類）？

    比對 asyncpg 的 SQLSTATE `23505` 而不是解析訊息字串：訊息會隨 PostgreSQL 的語系
    與版本變，SQLSTATE 是標準的一部分。
    """
    if not isinstance(error, IntegrityError):
        return False
    return getattr(getattr(error, "orig", None), "sqlstate", None) == "23505"


def _encode_cursor(sort_value: Any, row_id: str) -> str:
    if isinstance(sort_value, datetime):
        sort_value = sort_value.isoformat()
    raw = json.dumps([sort_value, row_id])
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode_cursor(cursor: str) -> tuple[Any, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        sort_value, row_id = json.loads(raw)
        parsed_id = uuid.UUID(str(row_id))
    except (ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
        raise LangException(400, PaginationError.INVALID_CURSOR) from exc

    if isinstance(sort_value, str):
        try:
            sort_value = datetime.fromisoformat(sort_value)
        except ValueError:
            pass

    return sort_value, parsed_id


def parse_uuid(value: str) -> uuid.UUID | None:
    """把對外的字串 id 轉成 UUID，格式不合法時回傳 None（不是丟例外）。

    呼叫端因此只需要處理「查無此筆」一種情況，不必各自防禦格式錯誤。
    """
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


def pagination_indexes(table_name: str) -> tuple[Index, ...]:
    """`get_page` 游標分頁用到的標準索引組合，供各資料表的 `__table_args__` 複用。

    **索引名稱在 PostgreSQL 是整個 schema 唯一的**，所以這裡要收 `table_name` 把它
    拼進名字裡；兩張表都叫 `is_disabled_created_at` 會在建立第二個時直接失敗。

    只給有 `is_disabled` 欄位的資料表用（items／roles／users）。
    """
    return (
        Index(f"ix_{table_name}_is_disabled_created_at", "is_disabled", desc("created_at")),
        Index(f"ix_{table_name}_created_at_id", desc("created_at"), desc("id")),
    )


def resolve_disabled_at(current_disabled_at: datetime | None, is_disabled: bool) -> datetime | None:
    """依 `is_disabled` 決定 `disabled_at`：停用時保留原本的停用時間（若有）否則蓋上現在時間；
    啟用時清空。"""
    if is_disabled:
        return current_disabled_at or utc_now()
    return None


def _normalize_for_compare(current_val: Any, new_val: Any) -> tuple[Any, Any]:
    if isinstance(current_val, uuid.UUID):
        return str(current_val), str(new_val)
    if isinstance(current_val, list) and isinstance(new_val, list):
        norm_current = [str(item) if isinstance(item, uuid.UUID) else item for item in current_val]
        norm_new = [str(item) if isinstance(item, uuid.UUID) else item for item in new_val]
        return norm_current, norm_new
    return current_val, new_val


class BaseTable(DeclarativeBase):
    # 主鍵是應用程式產生的 uuid4，不是資料庫的 BIGSERIAL。
    #
    # 理由是 id 對外可見（出現在 URL 與 API 回應裡），自增整數等於公開資料量、也讓人
    # 可以逐一遍歷帳號。
    #
    # 值由**欄位層級的 default** 在 INSERT 當下產生，所以剛 `cls(...)` 出來的實例上
    # `id` 還是 None —— 要讀 id 一律先 `flush()`（`create()` 就是這樣做的）。
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # 一律 naive UTC（見 shared/time.utc_now）。欄位型別也刻意是 `TIMESTAMP WITHOUT
    # TIME ZONE`：整個系統只存 UTC，讓資料庫多記一個永遠是 UTC 的時區只會讓
    # 「讀回來是 aware 還是 naive」隨驅動版本飄。
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=utc_now)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), default=None)

    seed_match_key: ClassVar[str | None] = None
    seed_data: ClassVar[list[dict]] = []

    @classmethod
    def detail_loaders(cls) -> Sequence[ExecutableOption]:
        """`find_detail_*`／`get_page`／`get_all` 要一併載入的關聯，預設沒有。

        回傳 `selectinload(...)` 這類 loader option。用 `selectinload` 而不是
        `joinedload` 是刻意的：前者對**已取回的那幾筆**另外發一次查詢，不會讓分頁的
        `LIMIT` 因為 JOIN 展開成多列而算錯筆數。要補的資料本身在 `to_detail()` 裡組。
        """
        return ()

    @classmethod
    def _apply_loaders(cls, statement: Select) -> Select:
        loaders = cls.detail_loaders()
        return statement.options(*loaders) if loaders else statement

    def to_dict(self) -> dict:
        """資料表欄位的原樣 dict，`id` 已轉成字串。

        **不含關聯資料**（見 `to_detail`），也不會過濾任何欄位 —— 敏感欄位的排除是
        `to_detail()` 的責任，那才是對外的形狀。
        """
        mapper = inspect(type(self))
        data: dict[str, Any] = {}
        for attribute in mapper.column_attrs:
            value = getattr(self, attribute.key)
            data[attribute.key] = str(value) if isinstance(value, uuid.UUID) else value
        data["id"] = str(self.id)
        return data

    def to_detail(self) -> dict:
        """對外的 dict 形狀。需要補關聯欄位或排除敏感欄位的資料表覆寫**這個**。

        命名慣例（整個專案共用，請勿破壞）：
        - `find_*` / `find_by_id`  → 回傳 ORM 實例，可直接存取欄位屬性
        - `find_detail_*`          → 回傳經過 `to_detail()` 加工的 dict
        """
        return self.to_dict()

    @classmethod
    def _coerce(cls, data: dict) -> dict:
        """把字串形式的 id 轉成 `uuid.UUID` 再交給驅動。

        專案內的 id 一路上都是字串（路由參數、`CurrentUser["id"]`、TypedDict 的欄位），
        而 asyncpg 對 `uuid` 欄位只收 `uuid.UUID` —— 沒有這層轉換，
        `create({"created_by_id": current_user["id"]})` 會在寫入當下丟
        `DataError: invalid input for query argument`，而錯誤訊息不會說是型別問題。
        """
        mapper = inspect(cls)
        coerced = dict(data)
        for key, value in data.items():
            column = mapper.columns.get(key)
            if column is None or not isinstance(column.type, UUID) or value is None:
                continue
            if isinstance(value, uuid.UUID):
                continue
            parsed = parse_uuid(value)
            if parsed is None:
                # 這裡丟 ValueError 而不是靜靜跳過：靜靜跳過會讓一個打錯的外鍵變成
                # 「這個欄位沒有被寫入」，症狀出現在很久以後的查詢結果裡。
                raise ValueError(f"{cls.__name__}.{key} 不是合法的 UUID：{value!r}")
            coerced[key] = parsed
        return coerced

    # ── 讀 ────────────────────────────────────────────────────────────────────

    @classmethod
    async def find_by_id(cls, id: str, session: AsyncSession | None = None) -> Self | None:
        # 回傳 Self 而非 BaseTable：呼叫端拿到具體子類，`user.nickname` 才有型別。
        row_id = parse_uuid(id)
        if row_id is None:
            return None
        return await resolve_session(session).get(cls, row_id)

    @classmethod
    async def find_detail_one(
        cls,
        *where: Condition,
        session: AsyncSession | None = None,
    ) -> dict | None:
        """取符合條件的第一筆並套用 `detail_loaders()` / `to_detail()`。

        **呼叫端必須自備條件。** 這裡只負責限制成一筆；沒有條件時回傳的是資料表掃描
        順序上的第一筆。以 id 取單筆請一律用下面的 `find_detail_by_id`。
        """
        statement = cls._apply_loaders(select(cls).where(*where)).limit(1)
        row = (await resolve_session(session).scalars(statement)).unique().first()
        return None if row is None else row.to_detail()

    @classmethod
    async def find_detail_by_id(cls, id: str, session: AsyncSession | None = None) -> dict | None:
        """以 id 取單筆並套用 `detail_loaders()`，回傳 **dict**。

        id 格式不合法時回傳 None（與 `find_by_id` 一致），呼叫端因此只需要處理
        「查無此筆」一種情況。
        """
        row_id = parse_uuid(id)
        if row_id is None:
            return None
        return await cls.find_detail_one(cls.id == row_id, session=session)

    @classmethod
    async def get_all(
        cls,
        *,
        where: Sequence[Condition] = (),
        order_by: Sequence[Any] | None = None,
        session: AsyncSession | None = None,
    ) -> SimpleListResult:
        """取回**全部**符合條件的資料，不分頁。回傳 `{list_data, count}`。

        給「下拉選單選項」這類天然有限、且呼叫端需要完整清單的情境使用。資料量會隨使用
        成長的列表請改用 `get_page`。

        與 `get_page` 拆開而不是共用一個 `limit: int | None` 參數，是因為兩者的回傳形狀
        完全不同（這裡沒有游標與 has_next），可避免將非分頁結果誤當成 `PaginatedResponse`。
        """
        # 預設順序與 get_page 一致：依建立時間由舊到新，並以 id 作為同時間的穩定
        # tie-breaker，避免同一份資料在兩個端點呈現不同順序。
        ordering = order_by or (cls.created_at.asc(), cls.id.asc())
        statement = cls._apply_loaders(select(cls).where(*where)).order_by(*ordering)
        rows = (await resolve_session(session).scalars(statement)).unique().all()

        list_data = [row.to_detail() for row in rows]
        return {"list_data": list_data, "count": len(list_data)}

    @classmethod
    async def get_page(
        cls,
        *,
        limit: int,
        cursor: str | None = None,
        direction: Literal["next", "prev"] = "next",
        sort_field: str = "created_at",
        where: Sequence[Condition] = (),
        session: AsyncSession | None = None,
    ) -> PagedResult:
        """游標（keyset）分頁。

        回傳 `{list_data, next_cursor, prev_cursor, has_next, has_previous, total_count}`。

        - `where`：會影響「符合條件的筆數」的條件（名稱關鍵字、狀態…）。它同時套用在
          資料查詢與 `total_count` 的 `COUNT(*)` 上，兩者才會一致。**游標條件刻意不進
          count**，否則 `total_count` 會隨著翻頁一直變小。
        - 補關聯資料由 `detail_loaders()` 負責，不在這裡。`selectinload` 只對這一頁
          實際取回的列另發一次查詢，不會隨候選筆數變貴。

        排序鍵是 `(sort_field, id)`。**tie-breaker 一定要有**：`created_at` 相同的兩筆
        若沒有第二個鍵，PostgreSQL 不保證兩次查詢給出同樣的順序，翻頁就會跳過或重複。

        游標的值取自 **ORM 實例**（`getattr(row, sort_field)` 與 `row.id`），不是
        `to_detail()` 產生的 dict —— 後者可以任意改寫 `id`（例如換成關聯對象的 id），
        存進游標就會在下一頁比對到別張表的鍵。
        """
        db = resolve_session(session)
        sort_column = getattr(cls, sort_field)
        going_backward = direction == "prev"

        conditions = list(where)
        if cursor is not None:
            sort_value, row_id = _decode_cursor(cursor)
            if going_backward:
                keyset = or_(
                    sort_column < sort_value,
                    and_(sort_column == sort_value, cls.id < row_id),
                )
            else:
                keyset = or_(
                    sort_column > sort_value,
                    and_(sort_column == sort_value, cls.id > row_id),
                )
            conditions.append(keyset)

        ordering = (
            (sort_column.desc(), cls.id.desc())
            if going_backward
            else (sort_column.asc(), cls.id.asc())
        )
        statement = (
            cls._apply_loaders(select(cls).where(*conditions)).order_by(*ordering).limit(limit + 1)
        )
        rows = list((await db.scalars(statement)).unique().all())

        there_is_more = len(rows) > limit
        rows = rows[:limit]
        if going_backward:
            rows.reverse()

        if cursor is None and not going_backward:
            has_previous, has_next = False, there_is_more
        elif cursor is None and going_backward:
            has_previous, has_next = there_is_more, False
        elif going_backward:
            has_previous, has_next = there_is_more, True
        else:
            has_previous, has_next = True, there_is_more

        next_cursor = (
            _encode_cursor(getattr(rows[-1], sort_field), str(rows[-1].id))
            if rows and has_next
            else None
        )
        prev_cursor = (
            _encode_cursor(getattr(rows[0], sort_field), str(rows[0].id))
            if rows and has_previous
            else None
        )

        # total_count 只套用 `where`，不套用游標條件（見上面的 docstring）。
        total_count = await db.scalar(select(func.count()).select_from(cls).where(*where)) or 0

        return {
            "list_data": [row.to_detail() for row in rows],
            "next_cursor": next_cursor,
            "prev_cursor": prev_cursor,
            "has_next": has_next,
            "has_previous": has_previous,
            "total_count": total_count,
        }

    # ── 寫 ────────────────────────────────────────────────────────────────────

    @classmethod
    async def create(cls, data: dict, session: AsyncSession | None = None) -> dict:
        db = resolve_session(session)
        row = cls(**cls._coerce(data))
        db.add(row)
        # flush 而不是 commit：交易邊界屬於呼叫端（HTTP middleware 或 `transaction()`），
        # 這裡自己 commit 會讓 `transaction()` 區塊裡的第一個寫入變成不可回滾。
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
        """逐欄位比對後只寫真正改變的欄位。

        沒有任何欄位真的改變時丟出 `NoChangeError`（由 server 轉成 204）。

        `also_changed` 給「這次更新還動到欄位以外的東西」的子類用（目前是 users 的
        角色指派）：欄位全都沒變、但關聯改了，仍然是一次真正的更新，不該回 204。
        """
        db = resolve_session(session)
        row = await cls.find_by_id(id, session=db)
        if row is None:
            return None
        if data or also_changed:
            changed = {}
            for key, value in cls._coerce(data or {}).items():
                current = getattr(row, key, None)
                norm_current, norm_value = _normalize_for_compare(current, value)
                if norm_current != norm_value:
                    changed[key] = value
            if not changed and not also_changed:
                raise NoChangeError()
            changed["updated_at"] = utc_now()
            for key, value in changed.items():
                setattr(row, key, value)
            await db.flush()
        return row.to_dict()

    @classmethod
    async def delete_by_id(cls, id: str, session: AsyncSession | None = None) -> dict | None:
        db = resolve_session(session)
        row = await cls.find_by_id(id, session=db)
        if row is None:
            return None
        result = row.to_dict()
        await db.delete(row)
        await db.flush()
        return result

    # ── Seed ─────────────────────────────────────────────────────────────────

    @classmethod
    async def prepare_seed_item(cls, item: dict) -> dict:
        return item

    @classmethod
    async def ensure_seed(cls, session: AsyncSession | None = None) -> None:
        """依 `seed_data` / `seed_match_key` 寫入初始資料。

        見 docs/extending.md「初始資料（Seed）」。

        - 有設 `seed_match_key`：每次都逐筆 upsert（`INSERT … ON CONFLICT DO UPDATE`），
          讓日後新增的欄位能補到已經跑起來的環境。**該欄位必須有唯一約束**，否則
          `ON CONFLICT` 無從判斷衝突，PostgreSQL 會直接報錯。那個嚴格是好事 ——
          它擋掉「match key 沒有唯一約束，於是每次啟動都多插一筆」。
        - 沒設：只在資料表完全空的時候整批 insert，不動既有資料。
        """
        if not cls.seed_data:
            return
        db = resolve_session(session)

        if cls.seed_match_key is not None:
            for item in cls.seed_data:
                prepared = await cls.prepare_seed_item(item)
                if cls.seed_match_key not in prepared:
                    raise ValueError(f"seed item missing match key: {cls.seed_match_key}")
                values = {"id": uuid.uuid4(), "created_at": utc_now(), **prepared}
                # created_at 不進 set_：它是「第一次寫進去的時間」，每次啟動都蓋掉的話
                # 預設排序（依 created_at）會在每次重啟後洗牌。
                updates = {key: value for key, value in prepared.items() if key != "created_at"}
                statement = pg_insert(cls).values(**values)
                await db.execute(
                    statement.on_conflict_do_update(
                        index_elements=[cls.seed_match_key],
                        set_=updates,
                    )
                )
            await db.flush()
            return

        existing = await db.scalar(select(func.count()).select_from(cls))
        if existing:
            return
        for item in cls.seed_data:
            prepared = await cls.prepare_seed_item(item)
            db.add(cls(**cls._coerce(prepared)))
        await db.flush()
