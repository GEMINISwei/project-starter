"""shared 層的整合測試需要一個真的 PostgreSQL。

刻意用「只存在於測試裡」的資料表來驗 `BaseTable` 的分頁、seed 與取單筆，而不是拿
UserTable 之類的正式 model：這些是 shared 的行為，測試不該綁在任何 domain model 的
欄位上，那些欄位改了不應該讓分頁測試壞掉。
"""

import os

import pytest_asyncio
from sqlalchemy import String, delete, select
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.session import configure_session_factory, create_engine, session_scope
from shared.db.table import BaseTable
from shared.time import utc_now
from tests.integration import require_postgres


class PagedRow(BaseTable):
    """只給分頁測試用的最小資料表。"""

    __tablename__ = "test_paged_rows"

    name: Mapped[str] = mapped_column(String)
    group: Mapped[str] = mapped_column(String)


class SeedRow(BaseTable):
    """給 `ensure_seed` 用的最小資料表。`seed_match_key` 由各測試自己覆寫。

    `code` 帶唯一約束是必要的，不是裝飾：`ensure_seed` 的 upsert 分岔用
    `INSERT … ON CONFLICT (code)`，沒有唯一約束時 PostgreSQL 無從判斷衝突。
    """

    __tablename__ = "test_seed_rows"

    code: Mapped[str] = mapped_column(String, unique=True)
    label: Mapped[str] = mapped_column(String)


class DetailRow(BaseTable):
    """給 `find_detail_by_id` 用的最小資料表，覆寫了 `to_detail()`。

    加工只做一次字串串接，不牽涉第二張表 —— 這裡要驗的是「基底類別有沒有正確地把
    條件與 `to_detail()` 組起來」，不是關聯載入本身。
    """

    __tablename__ = "test_detail_rows"

    name: Mapped[str] = mapped_column(String)

    def to_detail(self) -> dict:
        return {**self.to_dict(), "label": f"#{self.name}"}


async def _connect(model: type[BaseTable]):
    """連上 PostgreSQL、建好 `model` 的資料表並清空；沒有可用的資料庫就跳過測試。

    `create_all(tables=[…])` 只建這一張，不是整個 metadata —— 測試用的表與正式 model
    住在同一份 metadata 上，一次全建會讓 shared 層的測試莫名其妙地依賴 users／roles
    的 schema 是否還建得起來。
    """
    url = os.environ["POSTGRES_URL"]
    engine = create_engine(url)

    await require_postgres(engine, url)

    async with engine.begin() as connection:
        await connection.run_sync(
            BaseTable.metadata.create_all,
            # 從 metadata 取而不是 `model.__table__`：後者在 `DeclarativeBase` 上宣告成
            # `FromClause`，`create_all` 要的是 `Table`。
            tables=[BaseTable.metadata.tables[model.__tablename__]],
        )
        await connection.execute(delete(model))

    configure_session_factory(engine)
    return engine


async def _teardown(engine, model: type[BaseTable]) -> None:
    async with engine.begin() as connection:
        await connection.execute(delete(model))
    await engine.dispose()


@pytest_asyncio.fixture
async def paged_rows():
    """建立 5 筆 created_at 遞增的資料，回傳可直接呼叫 `get_page` 的 model 類別。

    `get_page` 預設以 created_at 遞增排序、`id` 作為同時間的 tie-breaker，所以這裡
    刻意讓每筆的 created_at 都不同，測試結果才是確定的。
    """
    engine = await _connect(PagedRow)

    base = utc_now()
    async with session_scope() as session:
        for index in range(5):
            session.add(
                PagedRow(
                    name=f"row-{index}",
                    group="a" if index % 2 == 0 else "b",
                    created_at=base.replace(microsecond=index * 1000),
                )
            )

    # 測試本體也要有一個 session（model 方法的 `session=None` 會取當前那個）。
    async with session_scope():
        yield PagedRow

    await _teardown(engine, PagedRow)


@pytest_asyncio.fixture
async def seed_row():
    """空的資料表與 `SeedRow`，並在結束時把 class variable 還原。

    `seed_data`／`seed_match_key` 是 ClassVar，測試裡改了不還原會漏到下一條測試 ——
    而那種汙染的症狀是「單獨跑會過、整批跑會壞」。
    """
    engine = await _connect(SeedRow)
    original = (SeedRow.seed_data, SeedRow.seed_match_key)

    async def rows() -> list[SeedRow]:
        from shared.db.session import active_session

        result = await active_session().scalars(select(SeedRow).order_by(SeedRow.code))
        return list(result.all())

    async with session_scope():
        yield SeedRow, rows

    SeedRow.seed_data, SeedRow.seed_match_key = original
    await _teardown(engine, SeedRow)


@pytest_asyncio.fixture
async def detail_rows():
    """3 筆資料，回傳 `(DetailRow, [id0, id1, id2])`。

    **必須不只一筆**：`find_detail_by_id` 少了條件時仍會回傳「第一筆」，
    只有一筆資料的測試會照樣通過。
    """
    engine = await _connect(DetailRow)

    ids = []
    async with session_scope() as session:
        for index in range(3):
            row = DetailRow(name=f"detail-{index}")
            session.add(row)
            # **要先 flush 才讀得到 id**：`id` 的預設值是欄位層級的 default，SQLAlchemy
            # 在 INSERT 當下才套用它，剛建構出來的實例上是 None。少了這一行，ids 會裝三個
            # `"None"` 字串，而測試會表現成「查不到那一筆」—— 看起來像 model 壞了。
            await session.flush()
            ids.append(str(row.id))

    async with session_scope():
        yield DetailRow, ids

    await _teardown(engine, DetailRow)


@pytest_asyncio.fixture
async def tied_rows():
    """5 筆 `created_at` **完全相同**的資料 —— 專門用來驗 tie-breaker。

    主要排序欄位無法區分任何一筆時，翻頁的正確性完全落在 `id` 這個 tie-breaker 上。
    游標若存錯 id（例如存成 `to_detail()` 改寫過的值），就會在這裡表現成跳過或重複。
    """
    engine = await _connect(PagedRow)

    same_moment = utc_now().replace(microsecond=0)
    async with session_scope() as session:
        for index in range(5):
            session.add(PagedRow(name=f"tie-{index}", group="a", created_at=same_moment))

    async with session_scope():
        yield PagedRow

    await _teardown(engine, PagedRow)
