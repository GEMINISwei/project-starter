"""請求紀錄的排除清單（`app/server.py` 的 `UNLOGGED_PATHS`）。

這支測試守的是一個兩邊都會安靜失敗的東西：清單漏掉 `/health`，log 就被每 10 秒一次的
healthcheck 淹掉；清單長太多，真實請求會悄悄不留紀錄，而這份 log 是這個專案唯一的
可觀測性（見 docs/operations.md）。所以正反兩面都要斷言。
"""

import logging
from collections.abc import Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.server import UNLOGGED_PATHS


class _StubConnection:
    async def execute(self, *_args, **_kwargs) -> None:
        return None

    async def __aenter__(self) -> _StubConnection:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        return None


class _StubEngine:
    """`/health` 只用到 `engine.connect()` 加一句 SELECT，給它這些就夠。

    ASGITransport 不會跑 lifespan，所以 `app.state.db_engine` 本來是不存在的。
    """

    def connect(self) -> _StubConnection:
        return _StubConnection()


@pytest.fixture
def records() -> Iterator[list[logging.LogRecord]]:
    """直接掛 handler 收 `api.timing` 的紀錄。

    不能用 pytest 的 `caplog`：那份 fixture 靠 root logger 收，而 `api.timing` 是
    `propagate = False`（`app/server.py`），紀錄根本不會往上傳，caplog 會一直是空的 ——
    測試於是永遠通過，包括在排除清單壞掉的時候。
    """
    collected: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            collected.append(record)

    logger = logging.getLogger("api.timing")
    handler = _Collector()
    logger.addHandler(handler)
    try:
        yield collected
    finally:
        logger.removeHandler(handler)


@pytest_asyncio.fixture
async def client(monkeypatch: pytest.MonkeyPatch):
    from app.server import app

    monkeypatch.setattr(app.state, "db_engine", _StubEngine(), raising=False)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_health_check_is_not_logged(client: AsyncClient, records: list[logging.LogRecord]):
    response = await client.get("/health")

    assert response.status_code == 200
    assert records == []


@pytest.mark.asyncio
async def test_other_requests_are_logged(client: AsyncClient, records: list[logging.LogRecord]):
    """排除清單不能誤傷一般請求 —— 連沒對到路由的也要留下紀錄。"""
    await client.get("/definitely-not-a-route")

    assert len(records) == 1
    assert "GET /definitely-not-a-route" in records[0].getMessage()
    assert " 404 " in records[0].getMessage()


def test_unlogged_paths_only_contains_liveness_probes():
    """清單長出第二種用途時要有人發現 —— 那等於「某些請求悄悄不留紀錄」的後門。"""
    assert UNLOGGED_PATHS == frozenset({"/health"})


@pytest.mark.asyncio
async def test_request_id_is_reused_when_upstream_sends_one(
    client: AsyncClient, records: list[logging.LogRecord]
):
    """沿用上游的 id 才串得起來 —— nginx、Next 與 API 是三段不同的行程。"""
    response = await client.get("/definitely-not-a-route", headers={"X-Request-ID": "abc123"})

    assert response.headers["X-Request-ID"] == "abc123"
    assert "[abc123]" in records[0].getMessage()


@pytest.mark.asyncio
async def test_request_id_is_generated_when_missing(
    client: AsyncClient, records: list[logging.LogRecord]
):
    response = await client.get("/definitely-not-a-route")

    generated = response.headers["X-Request-ID"]
    assert generated and generated != "-"
    assert f"[{generated}]" in records[0].getMessage()


@pytest.mark.asyncio
async def test_unsafe_request_id_is_replaced(
    client: AsyncClient, records: list[logging.LogRecord]
):
    """帶換行的值可以偽造出一整行假的請求紀錄，所以不合格的一律換掉而不是照抄。"""
    response = await client.get(
        "/definitely-not-a-route", headers={"X-Request-ID": "a b\tc"}
    )

    assert response.headers["X-Request-ID"] != "a b\tc"
    assert "a b" not in records[0].getMessage()
