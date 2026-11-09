"""模組之間的行程內事件 (`shared/events.py`)。

發布者在自己的 `public.py` 定義事件, 訂閱者在 manifest 的 `event_handlers` 註冊處理函式。
處理函式在發布者的交易裡同步執行: 能否決操作, 失敗時一起回滾 (見 docs/extending/module-events.md)。
"""

import os
import uuid
from dataclasses import dataclass
from typing import cast

import pytest
import pytest_asyncio
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Column, MetaData, Table, insert, select
from sqlalchemy.dialects.postgresql import UUID

from shared.db.session import active_session, configure_session_factory, create_engine
from shared.events import Event, EventBus, EventHandler, publish, use_event_bus
from shared.http.errors import BaseError, LangException, LangText
from shared.module import ModuleManifest
from shared.platform import platform_scope
from tests.integration import require_postgres, restore_session_factory
from tests.shared.minimal_app import create_minimal_app


@dataclass(frozen=True)
class Pinged(Event):
    source: str


class _ProbeError(BaseError):
    REJECTED = LangText(zh="被否決", en="Rejected")


def _recording_module(name: str, calls: list[str]) -> ModuleManifest:
    async def handle(event: Pinged) -> None:
        calls.append(f"{name}:{event.source}")

    return ModuleManifest(name, event_handlers=(EventHandler(Pinged, handle),))


def _publisher_module() -> ModuleManifest:
    router = APIRouter(prefix="/publisher")

    @router.post("/ping")
    async def ping_route() -> dict[str, bool]:
        await publish(Pinged(source="route"))
        return {"ok": True}

    return ModuleManifest("publisher", routers=(router,))


async def _post_ping(*subscribers: ModuleManifest) -> int:
    application = create_minimal_app(_publisher_module(), *subscribers)
    transport = ASGITransport(app=application, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/publisher/ping")
    return response.status_code


@pytest.mark.asyncio
async def test_publish_runs_handlers_registered_in_manifests(calls: list[str]):
    status = await _post_ping(_recording_module("subscriber", calls))

    assert status == 200
    assert calls == ["subscriber:route"]


@pytest.mark.asyncio
async def test_handlers_run_in_enabled_module_order(calls: list[str]):
    """順序跟著啟用清單, 不隨註冊時的雜湊或 import 順序變動。"""
    status = await _post_ping(_recording_module("first", calls), _recording_module("second", calls))

    assert status == 200
    assert calls == ["first:route", "second:route"]


@pytest.mark.asyncio
async def test_publish_without_handlers_does_nothing(calls: list[str]):
    assert await _post_ping() == 200
    assert calls == []


@pytest.mark.asyncio
async def test_handler_error_propagates_to_publisher():
    """處理函式可以否決操作: 它丟的錯誤原樣回到發布端, 不被吞掉。"""

    async def reject(_event: Pinged) -> None:
        raise LangException(409, _ProbeError.REJECTED)

    with use_event_bus(EventBus([EventHandler(Pinged, reject)])):
        with pytest.raises(LangException) as exc_info:
            await publish(Pinged(source="direct"))

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_publish_without_event_bus_raises():
    """沒有入口設定訂閱表時直接報錯: 默默略過的話, 訂閱者的連動規則會悄悄失效。"""
    with pytest.raises(RuntimeError):
        await publish(Pinged(source="nowhere"))


def test_create_app_rejects_handler_for_non_event_type():
    class NotAnEvent:
        pass

    async def handle(_event: Event) -> None:
        return None

    bad = ModuleManifest(
        "bad", event_handlers=(EventHandler(cast(type[Event], NotAnEvent), handle),)
    )

    with pytest.raises(RuntimeError):
        create_minimal_app(bad)


@pytest.mark.asyncio
async def test_platform_scope_provides_session_and_event_bus(calls: list[str]):
    """非 HTTP 入口 (CLI、worker) 經過同一個 scope, 拿到的執行環境與請求相同。"""
    with restore_session_factory():
        async with platform_scope(
            [_recording_module("subscriber", calls)], "postgresql+asyncpg://localhost/unused"
        ) as session:
            assert active_session() is session
            await publish(Pinged(source="cli"))

    assert calls == ["subscriber:cli"]


@pytest.fixture
def calls() -> list[str]:
    return []


# ── 處理函式與發布者在同一個交易 ────────────────────────────────────────────────

_metadata = MetaData()
_audit = Table("test_event_audit", _metadata, Column("id", UUID(as_uuid=True), primary_key=True))


@pytest_asyncio.fixture
async def audit_engine():
    url = os.environ["POSTGRES_URL"]
    engine = create_engine(url)
    await require_postgres(engine, url)
    async with engine.begin() as connection:
        await connection.run_sync(_metadata.drop_all)
        await connection.run_sync(_metadata.create_all)
    with restore_session_factory():
        configure_session_factory(engine)
        yield engine
    async with engine.begin() as connection:
        await connection.run_sync(_metadata.drop_all)
    await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_handler_writes_roll_back_with_publisher(audit_engine):
    """發布端在處理函式寫入之後失敗, 處理函式的寫入也要一起撤銷。"""

    async def write_audit(_event: Pinged) -> None:
        await active_session().execute(insert(_audit).values(id=uuid.uuid4()))

    router = APIRouter(prefix="/publisher")

    @router.post("/ping-then-fail")
    async def ping_then_fail_route() -> dict[str, bool]:
        await publish(Pinged(source="route"))
        raise LangException(409, _ProbeError.REJECTED)

    application = create_minimal_app(
        ModuleManifest("publisher", routers=(router,)),
        ModuleManifest("auditor", event_handlers=(EventHandler(Pinged, write_audit),)),
    )
    transport = ASGITransport(app=application, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/publisher/ping-then-fail")

    assert response.status_code == 409
    async with audit_engine.connect() as connection:
        assert (await connection.execute(select(_audit))).all() == []
