"""引擎、連線池與「這次請求用哪個 session」。

SQLAlchemy 的 session 不是行程層級的單例 —— 它代表一段**工作單元**（unit of work），
有自己的交易與 identity map。但本專案的 model 方法
（`BaseTable.create`、`find_by_id`…）刻意維持「不必逐層傳 session」的呼叫方式，
否則每個 service 函式都要多接一個參數往下傳，而那正是這個模板一開始就避開的樣板碼。

折衷是一個 ContextVar：

- HTTP 請求由 `app/server.py` 的 middleware 開一個 session 並設進 `_current_session`，
  請求結束時 commit（例外則 rollback）。
- 不走 HTTP 的入口（WebSocket handshake、`scripts/db.py`、migration runner）自己用
  `session_scope()` 開一段。
- model 方法收到 `session=None` 時就取當前 session；明確傳了就用傳進來的那個
  （`transaction()` 的用法）。

**沒有任何一層會偷偷幫你開 session。** `active_session()` 在沒有 session 時直接丟
RuntimeError，而不是自己開一個 —— 後者會讓「忘了進入 session scope」的程式碼跑得好好的，
卻每個操作各自成為一個交易，`transaction()` 的原子性保證就悄悄消失了。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_current_session: ContextVar[AsyncSession | None] = ContextVar("current_session", default=None)

_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """建立 asyncpg 引擎。

    `pool_pre_ping` 一定要開：容器化部署裡 PostgreSQL 會被重啟、連線也會被中間的
    proxy 掐掉，而池子裡的死連線只有在**下一次查詢**時才會表現成
    `ConnectionDoesNotExistError` —— 也就是變成使用者眼前的 500，而不是一次無聲的重連。
    """
    return create_async_engine(
        url,
        echo=echo,
        pool_pre_ping=True,
        # 預設的 5 + 10 對單機部署已經夠用；重點是設個上限，別讓突發流量把
        # PostgreSQL 的 max_connections（預設 100）吃光而讓 migrate/psql 連不進去。
        pool_size=5,
        max_overflow=10,
    )


def configure_session_factory(engine: AsyncEngine) -> None:
    """安裝行程層級的 session factory。由 lifespan 與 CLI 腳本呼叫。"""
    global _session_factory
    _session_factory = async_sessionmaker(
        engine,
        # 不要 expire_on_commit：commit 之後 ORM 實例的欄位會被標成過期，
        # 下一次存取要重新查一次資料庫 —— 而 `create()` 正是「commit 後讀 id」，
        # 那會變成每筆新增都多一次 SELECT，甚至在 session 已關閉時直接爆
        # DetachedInstanceError。
        expire_on_commit=False,
        autoflush=True,
    )


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("session factory 尚未安裝，請先呼叫 configure_session_factory()")
    return _session_factory


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """開一段 session 並設為當前 session；正常結束時 commit，例外時 rollback。

    HTTP 請求由 middleware 呼叫，其餘入口（WS handshake、CLI、migration）自己呼叫。
    可以巢狀：內層會建立自己的 session，離開時把 ContextVar 還原成外層那個。
    """
    async with session_factory()() as session:
        token = _current_session.set(session)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            _current_session.reset(token)


def active_session() -> AsyncSession:
    """取得當前 session，沒有就是程式錯誤（見模組 docstring）。"""
    session = _current_session.get()
    if session is None:
        raise RuntimeError(
            "目前沒有可用的資料庫 session。"
            "HTTP 之外的入口（WebSocket、CLI、背景工作）必須自己包在 session_scope() 裡。"
        )
    return session


def resolve_session(session: AsyncSession | None) -> AsyncSession:
    """model 方法的 `session=None` 語義：沒傳就用當前 session。"""
    return session if session is not None else active_session()
