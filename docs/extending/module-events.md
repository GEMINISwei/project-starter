# 模組事件

被別的模組參照的資料有變動時，用事件通知參照者，例如：停用使用者時取消他的訂單、刪除商品前確認沒有未出貨的訂單、
同步存在別的模組的去正規化副本。被參照的模組不能反過來 import 參照它的模組（[規則](../architecture.md#反方向的需求)），
所以由它發布事件、參照者訂閱。

## 什麼時候用事件、什麼時候用 public 函式

| 情境 | 用什麼 |
|---|---|
| 我需要對方的資料或能力（參照的一方問被參照的一方） | 對方 `public.py` 的函式 |
| 我的資料變了，參照我的模組可能要跟著做事（被參照的一方通知參照的一方） | 發布事件 |
| 只是「還有人在用就不准刪」 | 先用外鍵的 `RESTRICT`，平台會轉成 409；需要更具體的訊息才用事件否決 |

## 定義與發布（被參照的模組）

事件由**發布者**定義，從自己的 `public.py` 轉出，只帶識別資料（id），不帶整份資料：訂閱者需要更多時自己去查，事件的形狀才不會被
訂閱者綁住。

```python
# modules/users/events.py
from dataclasses import dataclass

from shared.events import Event


@dataclass(frozen=True)
class UserDisabled(Event):
    user_id: str


# modules/users/public.py
from .events import UserDisabled

# modules/users/service.py —— 在資料寫入之後發布
from shared.events import publish

await UserTable.update_by_id(id=target_id, data={"is_disabled": True})
await publish(UserDisabled(user_id=target_id))
```

## 訂閱（參照的模組）

```python
# modules/orders/subscriptions.py
from modules.users.public import UserDisabled


async def cancel_open_orders(event: UserDisabled) -> None:
    await OrderTable.cancel_open_by_user(event.user_id)


# modules/orders/manifest.py
from shared.events import EventHandler

MODULE = ModuleManifest(
    name="orders",
    ...,
    event_handlers=(EventHandler(UserDisabled, cancel_open_orders),),
)
```

- 註冊的不是 `Event` 的子類別時，建立 app 就會失敗。
- 同一個事件有多個訂閱者時，依 `app/registry.py` 的 `ENABLED_MODULES` 順序執行。不要依賴這個順序寫業務規則，
  需要先後時合併成一個處理函式。

## 處理函式的規則

- **在發布者的交易裡同步執行。** 寫入跟發布者一起提交或回滾；處理函式丟出錯誤（例如 `LangException(409, ...)`）
  會回到發布端，整個操作被否決。
- **不做外部副作用**：寄信、呼叫外部服務、寫檔。交易之後可能回滾，信卻已經寄出；這類工作在處理函式裡排進背景工作佇列
  （[背景工作](background-jobs.md)，排入佇列的寫入一樣在同一個交易裡）。
- **不再發布會繞回自己的事件**，避免無窮遞迴。
- 處理函式會讓發布端變慢，只做必要的查詢與寫入。

## 非 HTTP 的入口

HTTP 請求的訂閱表由 middleware 設定。CLI 與背景工作一律經過 `platform_scope()`（[說明](../architecture.md#非-http-的入口)）；
沒有訂閱表就 `publish()` 會直接報錯，不會默默略過。

## 測試

- 發布端：在 service 測試裡 monkeypatch 該 service 模組的 `publish`，斷言發布了哪個事件。
- 訂閱端：直接呼叫處理函式，或用 `use_event_bus(EventBus([...]))` 包住再 `publish()`。範例見
  `apps/api/tests/shared/test_events.py`。
