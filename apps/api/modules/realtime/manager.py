"""WebSocket 連線登記簿。

刻意用行程內記憶體實作，不引入 Redis pub/sub：理由與 `shared/http/rate_limit.py` 相同 ——
這是一個要能 `make dev` 就跑起來的模版。代價要講清楚 ——

- **多個後端副本時，事件只送得到「跟發送者同一個副本」的連線**。使用者連在副本 A、
  事件由副本 B 發出時，訊息不會送達，而且是**靜默**的：沒有例外、沒有 log，
  畫面就只是沒有更新。這比限流的代價更難察覺，因為沒有任何回饋。
- 重啟後所有連線消失（客戶端會重連，見前端 `WSManager`）。

單一副本（本模版 compose 的預設）不受影響。要水平擴展時，把這個類別換成以 Redis pub/sub
轉發的實作即可：對外只有 `connect` / `disconnect` / `send_to_user` 三個方法，
呼叫端（`modules/push/dispatcher.py` 與各 module 的 service）不需要改。

另有一種常見誤解值得寫下來：把 `send_to_user` 當成可靠投遞。它不是 —— 送不出去的連線
會被直接移除（見下），不會重試也不會排隊。需要「一定要送到」的訊息請走資料庫或推播。
"""

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, set[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        if user_id in self._connections:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                del self._connections[user_id]

    async def send_to_user(self, user_id: str, message: dict) -> None:
        sockets = set(self._connections.get(user_id, set()))
        for ws in sockets:
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(user_id, ws)


ws_manager = ConnectionManager()
