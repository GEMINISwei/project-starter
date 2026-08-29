"""推播內容的語系。

`/push/test` 的標題與內文是**模板提供的文案**（不是使用者輸入），所以要跟著
Accept-Language 走。理由與 `tests/modules/items/test_ws_message.py` 相同：這類文字沒有
`LangException` 幫忙，寫死了也不會有任何檢查抱怨，而它會直接出現在使用者的通知列上。
"""

import pytest
from httpx import AsyncClient

from app.permissions import Permission
from modules.push import service as push_service
from modules.push.dispatcher import NotificationPayload

from ..helpers import authenticate

USERS = {
    "member": {
        "id": "user-member",
        "nickname": "Member",
        "role_ids": [],
        # /push/test 只要求「有登入」—— 任何人都該能確認自己的推播設定。
        "permissions": [Permission.USER_READ],
        "is_disabled": False,
    },
}


@pytest.fixture(autouse=True)
def _current_users(set_current_users):
    set_current_users(USERS)


@pytest.fixture
def sent_payloads(monkeypatch: pytest.MonkeyPatch) -> list[NotificationPayload]:
    """攔下實際送出的 payload，不真的去打 Web Push。"""
    payloads: list[NotificationPayload] = []

    async def fake_send_to_user(user_id, payload):
        payloads.append(payload)

    monkeypatch.setattr(
        push_service.NotificationDispatcher, "send_to_user", staticmethod(fake_send_to_user)
    )

    return payloads


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("accept_language", "expected_title", "expected_body"),
    [
        ("zh-TW", "推播測試", "推播功能正常運作"),
        ("en-US", "Push test", "Push notifications are working"),
    ],
)
async def test_test_push_payload_follows_accept_language(
    client: AsyncClient, sent_payloads, accept_language, expected_title, expected_body
):
    authenticate(client, "member")

    response = await client.post("/api/push/test", headers={"Accept-Language": accept_language})

    assert response.status_code == 200
    assert len(sent_payloads) == 1
    assert sent_payloads[0].title == expected_title
    assert sent_payloads[0].body == expected_body


@pytest.mark.asyncio
async def test_test_push_requires_authentication(client: AsyncClient, sent_payloads):
    response = await client.post("/api/push/test")

    assert response.status_code == 401
    assert sent_payloads == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("owner_id", "expected_ok"),
    [("user-member", True), ("someone-else", False)],
)
async def test_remove_subscription_reports_whether_it_removed_anything(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, owner_id, expected_ok
):
    """退訂別人的 endpoint 要回 ok=false，不能謊報成功。

    endpoint 是瀏覽器給的不透明字串，所以這裡刻意不回 403/404（那等於讓任何登入者
    拿它探測某個 endpoint 存不存在）。但也不能回 ok=true —— 呼叫端會以為自己退訂了。
    """
    deleted: list[str] = []

    async def fake_find(endpoint: str):
        return {"id": "sub-1", "user_id": owner_id, "endpoint": endpoint}

    async def fake_delete(id: str):
        deleted.append(id)

    monkeypatch.setattr(
        push_service.PushSubscriptionTable, "find_detail_by_endpoint", staticmethod(fake_find)
    )
    monkeypatch.setattr(
        push_service.PushSubscriptionTable, "delete_by_id", staticmethod(fake_delete)
    )
    authenticate(client, "member")

    response = await client.delete(
        "/api/push/subscriptions", params={"endpoint": "https://push.example/abc"}
    )

    assert response.status_code == 200
    assert response.json()["ok"] is expected_ok
    assert deleted == (["sub-1"] if expected_ok else [])
