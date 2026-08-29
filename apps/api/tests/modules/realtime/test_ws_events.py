"""釘住 WebSocket 事件的型別契約。

`WsEventType` 是唯一來源，經由 `GET /ws/events` 進入 OpenAPI，前端用
`Record<WsEventType, handler>` 窮盡處理（少一個 key 就編譯失敗）。這裡守住後端這一側：
端點要如實列出所有事件，而 service 送出的必須都是合法的 enum 成員。
"""

import pytest
from httpx import AsyncClient

from app.permissions import Permission
from modules.realtime.schema import WsEvent, WsEventType

from ..helpers import authenticate

USERS = {
    "member": {
        "id": "user-member",
        "nickname": "Member",
        "role_ids": [],
        "permissions": [Permission.USER_READ],
        "is_disabled": False,
    },
}


@pytest.fixture(autouse=True)
def _current_users(set_current_users):
    set_current_users(USERS)


@pytest.mark.asyncio
async def test_ws_events_lists_every_event_type(client: AsyncClient):
    authenticate(client, "member")

    response = await client.get("/api/ws/events")

    assert response.status_code == 200
    body = response.json()
    assert {item["value"] for item in body["list_data"]} == {event.value for event in WsEventType}
    assert body["count"] == len(WsEventType)


@pytest.mark.asyncio
async def test_ws_events_requires_authentication(client: AsyncClient):
    """事件目錄不是公開資訊，未登入不該讀得到。"""
    response = await client.get("/api/ws/events")

    assert response.status_code == 401


def test_ws_event_type_is_not_empty_without_domain_features():
    """至少要有一個不屬於任何功能的事件。

    若 `WsEventType` 裡只保留可選功能的事件，移除它們後 enum 會變成空的，前端
    `Record<WsEventType, …>` 會退化成
    `Record<never, …>` —— WS 機制與它的擴充範例就一起失效了。
    """
    domain_neutral = {event for event in WsEventType if event.value == "system_announcement"}

    assert domain_neutral, "WsEventType 必須保留至少一個 domain-neutral 事件"


def test_ws_event_model_rejects_unknown_type():
    """信封本身也受 pydantic 驗證，打錯字不會被送出去。"""
    with pytest.raises(ValueError):
        WsEvent(type="not_a_real_event")  # type: ignore[arg-type]
