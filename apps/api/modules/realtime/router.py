from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect

from shared.auth.contracts import CurrentUser, CurrentUserResolver
from shared.auth.dependency import check_user_permission, is_current_auth_version
from shared.auth.tokens import WS_TICKET_TTL_SECONDS, create_ws_ticket, parse_ws_ticket
from shared.db.session import session_scope

from .manager import ws_manager
from .schema import WsEventInfo, WsEventList, WsEventType, WsTicket

router = APIRouter(tags=["ws"])


@router.get("/ws/events")
async def get_ws_event_types_route(
    _=Depends(check_user_permission()),
) -> WsEventList:
    """列出這個 WebSocket 可能推送的所有事件種類。"""
    return WsEventList(
        list_data=[WsEventInfo(value=event) for event in WsEventType],
        count=len(WsEventType),
    )


@router.post("/ws/ticket")
async def create_ws_ticket_route(
    request: Request,
    current_user: CurrentUser = Depends(check_user_permission()),
) -> WsTicket:
    """簽發開啟 WebSocket 用的短效憑證，帶在 `GET /ws` 的 `ticket` query 參數上。

    有效期見回應的 `expires_in`（秒）。重設密碼會讓已簽發的 ticket 立即失效。
    """
    return WsTicket(
        # 帶上簽發當下的 auth_version：重設密碼後，這張 ticket 連同 session token 一起失效。
        ticket=create_ws_ticket(
            current_user["username"],
            request.app.state.env,
            auth_version=current_user["auth_version"],
        ),
        expires_in=WS_TICKET_TTL_SECONDS,
    )


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    ticket: str = Query(...),
) -> None:
    try:
        env = websocket.app.state.env
        # 只接受 ws 型別的 ticket；session token 拿來這裡會被 parse_ws_ticket 拒絕。
        ticket_data = parse_ws_ticket(ticket, env)
        # `app.state` 上的東西型別是 Any，取出時明確標上契約才真的拿回型別檢查 ——
        # 否則下面的 `user["id"]`、`user["is_disabled"]` 完全不受 mypy 管
        #（同 shared/auth/dependency.py 取 resolver 的寫法）。
        resolver: CurrentUserResolver = websocket.app.state.current_user_resolver
        # WebSocket 不經過 HTTP middleware，所以沒有現成的 session（見
        # shared/db/session.py）。**只包住 handshake 這幾行**，不要包整個連線 ——
        # 連線可以活好幾個小時，握著一條連線池的連線不放，幾十個閒置的分頁就能把
        # PostgreSQL 的連線數吃光。
        async with session_scope():
            user = await resolver(ticket_data["username"])
        if not user or user["is_disabled"]:
            await websocket.close(code=1008)
            return
        # 與 HTTP 端用同一套判斷。只擋 HTTP 而漏掉這裡，等於留一條「重設密碼後仍可用
        # 舊 ticket 連上、而且連線一旦建立就長期保持」的路。
        if not is_current_auth_version(ticket_data, user):
            await websocket.close(code=1008)
            return
        user_id: str = user["id"]
    except Exception:
        await websocket.close(code=1008)
        return

    await ws_manager.connect(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()  # 保持連線，斷線時拋出 WebSocketDisconnect
    except WebSocketDisconnect:
        ws_manager.disconnect(user_id, websocket)
