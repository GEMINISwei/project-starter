"""WebSocket 的事件種類與訊息形狀。

`WsEventType` 是前後端共用的唯一事實來源：它透過 `GET /ws/events` 進入 OpenAPI，
`make gen-types` 產成前端的字串聯集型別，`WSManager.tsx` 用 `Record<WsEventType, …>`
窮盡處理。在這裡新增或刪除事件而前端沒跟上，`tsc` 會失敗。

注意：這個檔案裡 **model 與 enum 的 docstring 會變成 OpenAPI 的 description**，
出現在 `/docs` 與產生的 TS 型別檔裡。只寫呼叫端需要知道的事，內部說明寫在這裡。
"""

from enum import StrEnum

from pydantic import BaseModel

from shared.http.schema import SimpleListResponse


class WsEventType(StrEnum):
    """伺服器主動推送的 WebSocket 事件種類。"""

    # --- 通用事件：請保留 ---
    # 這個成員刻意不屬於任何功能。少了它，移除下方範例事件後整個 enum 會變成空的，
    # 前端 `Record<WsEventType, …>` 退化成 `Record<never, …>`，WS 機制與 docs/extending.md 的
    # 「新增 WebSocket 事件」擴充流程就一起失效。
    #
    # 本身沒有內建的發送端（模板不預設任何廣播情境）。要送的話從 `modules.realtime.public`
    # 取 `WsEvent`／`WsEventType`／`ws_manager`，組出事件後 `send_to_user`／`broadcast`，
    # 完整範例見 `modules/items/service.py` 的 `create_item`。
    # `message` 不可傳字面字串（`tests/test_i18n_text_usage.py` 會擋）——
    # 這個事件的內容預期是管理者自己打的字，當成參數傳進來。
    SYSTEM_ANNOUNCEMENT = "system_announcement"

    # --- 範例模組（`modules/items/`）的事件：移除範例時一併刪除 ---
    # 實際的發送端在 `modules/items/service.py` 的 `create_item`，那裡是「怎麼送事件」的
    # 完整範例（含通知失敗不該讓主要操作失敗的處理）。
    ITEM_CREATED = "item_created"


class WsTicket(BaseModel):
    ticket: str
    expires_in: int


class WsEvent(BaseModel):
    """透過 WebSocket 推送的訊息本體。

    兩個欄位都是選填，各事件只填自己用得到的那個。`message` 給沒有對應 REST 資源
    可查的事件用（例如 SYSTEM_ANNOUNCEMENT 的公告內容）。

    請保持精簡：收到事件後需要資料時，回頭打 REST 端點查（例如列表變更就
    `router.refresh()`），不要把 WS 訊息養成第二套要各自維護的資料契約。
    """

    type: WsEventType
    from_nickname: str | None = None
    message: str | None = None


class WsEventInfo(BaseModel):
    value: WsEventType


class WsEventList(SimpleListResponse["WsEventInfo"]):
    pass
