"""請求裡發生外鍵違反時, 平台統一回 409 與語系化的訊息, 而不是 500。

模組只要在資料庫宣告 `RESTRICT`, 不必各自攔 `IntegrityError` (見 docs/architecture.md
〈反方向的需求〉)。資料表只存在於這個測試, 用獨立的 `MetaData`, 不汙染正式 model 的那一份。
"""

import os
import uuid

import pytest
import pytest_asyncio
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Column, ForeignKey, MetaData, Table, delete, insert, update
from sqlalchemy.dialects.postgresql import UUID

from shared.db.session import active_session, configure_session_factory, create_engine
from shared.db.table import ForeignKeyError
from shared.module import ModuleManifest
from tests.integration import require_postgres, restore_session_factory
from tests.shared.minimal_app import create_minimal_app

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_metadata = MetaData()
parents = Table("test_fk_parents", _metadata, Column("id", UUID(as_uuid=True), primary_key=True))
children = Table(
    "test_fk_children",
    _metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
    Column(
        "parent_id",
        UUID(as_uuid=True),
        ForeignKey("test_fk_parents.id", ondelete="RESTRICT"),
    ),
)

PARENT_ID = uuid.uuid4()
CHILD_ID = uuid.uuid4()


def _router() -> APIRouter:
    router = APIRouter(prefix="/fk")

    @router.delete("/parent")
    async def delete_parent_route() -> dict[str, bool]:
        await active_session().execute(delete(parents).where(parents.c.id == PARENT_ID))
        return {"ok": True}

    @router.post("/child")
    async def insert_child_route() -> dict[str, bool]:
        await active_session().execute(
            insert(children).values(id=uuid.uuid4(), parent_id=uuid.uuid4())
        )
        return {"ok": True}

    @router.patch("/child")
    async def update_child_route() -> dict[str, bool]:
        await active_session().execute(
            update(children).where(children.c.id == CHILD_ID).values(parent_id=uuid.uuid4())
        )
        return {"ok": True}

    @router.post("/duplicate-parent")
    async def duplicate_parent_route() -> dict[str, bool]:
        await active_session().execute(insert(parents).values(id=PARENT_ID))
        return {"ok": True}

    return router


@pytest_asyncio.fixture
async def client():
    url = os.environ["POSTGRES_URL"]
    engine = create_engine(url)
    await require_postgres(engine, url)

    async with engine.begin() as connection:
        await connection.run_sync(_metadata.drop_all)
        await connection.run_sync(_metadata.create_all)
        await connection.execute(insert(parents).values(id=PARENT_ID))
        await connection.execute(insert(children).values(id=CHILD_ID, parent_id=PARENT_ID))

    with restore_session_factory():
        configure_session_factory(engine)
        application = create_minimal_app(ModuleManifest("fk", routers=(_router(),)))
        transport = ASGITransport(app=application, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http

    async with engine.begin() as connection:
        await connection.run_sync(_metadata.drop_all)
    await engine.dispose()


async def test_deleting_referenced_row_returns_409_still_in_use(client: AsyncClient):
    response = await client.delete("/api/fk/parent")

    assert response.status_code == 409
    assert response.json() == {"detail": ForeignKeyError.STILL_REFERENCED.value.zh}


async def test_inserting_missing_reference_returns_409_not_found(client: AsyncClient):
    response = await client.post("/api/fk/child", headers={"Accept-Language": "en"})

    assert response.status_code == 409
    assert response.json() == {"detail": ForeignKeyError.REFERENCE_NOT_FOUND.value.en}


async def test_updating_to_missing_reference_returns_409_not_found(client: AsyncClient):
    response = await client.patch("/api/fk/child")

    assert response.status_code == 409
    assert response.json() == {"detail": ForeignKeyError.REFERENCE_NOT_FOUND.value.zh}


async def test_other_integrity_errors_are_not_translated(client: AsyncClient):
    """唯一約束等其他完整性錯誤照舊: 該由模組自己判斷 (例: users 的帳號重複), 平台不猜。"""
    response = await client.post("/api/fk/duplicate-parent")

    assert response.status_code == 500
