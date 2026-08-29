"""給其他後端 module 使用的公開介面。

**目前 repo 內沒有消費者，這是刻意的**：推播是「已接好但沒有業務在用」的機制，
而這裡就是 docs/extending.md「使用 Web Push 推播」教你 import 的那個入口 ——
`modules/push/service.py` 自己走相對 import（同模組內部），所以真正的第一個消費者
會是下游寫的功能模組。

沒有這行說明的話，它看起來就跟「忘了刪的死碼」一模一樣 ——
而後端沒有 knip 那種工具，分辨不出「刻意留的」與「忘了刪的」。
"""

from .dispatcher import NotificationDispatcher, NotificationPayload

__all__ = ["NotificationDispatcher", "NotificationPayload"]
