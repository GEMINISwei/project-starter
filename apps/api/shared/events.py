"""模組之間的行程內事件。

給「被參照的一方要通知參照者」用 (停用使用者時連動取消訂單、刪除前檢查有沒有人在用、
同步去正規化的副本): 被參照的模組不能反過來 import 參照它的模組, 改由它發布事件、
參照者訂閱。

- 事件由**發布者**定義在自己的 `public.py` (繼承 `Event`), 訂閱者 import 它 ——
  依賴方向因此與外鍵方向一致。
- 訂閱者在 manifest 的 `event_handlers` 註冊, 組裝時依啟用清單排好順序。
- 處理函式在發布者的交易裡**同步**執行: 丟出錯誤就回到發布端 (可以否決操作),
  寫入也與發布者一起提交或回滾。寄信、呼叫外部服務這類要等資料確定寫入才做的事
  不放在這裡 (見 docs/extending/module-events.md)。

訂閱表每個 app 一份 (同權限目錄), 由入口設定成「目前的」: HTTP 請求由 middleware 設定,
非 HTTP 入口經過 `shared/platform.py` 的 `platform_scope()`。
"""

from collections.abc import Awaitable, Callable, Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Event:
    """所有事件的基底。子類別用 `@dataclass(frozen=True)`, 只帶 id 這類識別資料。"""


@dataclass(frozen=True)
class EventHandler:
    """一筆訂閱: 發生 `event` (含子類別) 時呼叫 `handle`。"""

    event: type[Event]
    handle: Callable[[Any], Awaitable[None]]


class EventBus:
    """一個 app 的訂閱表。`handlers` 的順序就是執行順序。"""

    def __init__(self, handlers: Iterable[EventHandler]) -> None:
        self._handlers = tuple(handlers)

    async def dispatch(self, event: Event) -> None:
        for handler in self._handlers:
            if isinstance(event, handler.event):
                await handler.handle(event)


_current_bus: ContextVar[EventBus | None] = ContextVar("current_event_bus", default=None)


@contextmanager
def use_event_bus(bus: EventBus) -> Iterator[None]:
    """在這段期間把 `bus` 設成目前的訂閱表。由入口呼叫, 模組不直接用。"""
    token = _current_bus.set(bus)
    try:
        yield
    finally:
        _current_bus.reset(token)


async def publish(event: Event) -> None:
    """把事件交給目前訂閱表裡的處理函式, 依序執行完才返回。

    **沒有訂閱表就報錯**, 不是略過: 略過的話訂閱者的連動規則會悄悄失效, 而症狀出現在很久
    以後的資料裡 (理由同 `active_session()`)。
    """
    bus = _current_bus.get()
    if bus is None:
        raise RuntimeError(
            "目前沒有事件訂閱表。HTTP 之外的入口 (CLI、背景工作) 必須包在 platform_scope() 裡。"
        )
    await bus.dispatch(event)
