"""**範例模組**的 WS 事件文案。移除範例時整個檔案一併刪除。

守的是「送到使用者眼前的文字要跟著 Accept-Language 走」。這條特別容易漏，因為它不是
錯誤訊息 —— 沒有 `LangException` 幫忙，寫成 f-string 也不會有任何檢查抱怨。

而且前端幫不上忙：`modules/items/realtime.ts` 是 `event.message ?? t("itemCreated")`，
後端一給 message，前端的字典就完全用不到。後端送中文，英文使用者就看到中文。
"""

import pytest

from modules.items import service as item_service
from modules.items.model import ItemTable
from modules.items.schema import ItemCreate
from shared.http.errors import Language, current_language


@pytest.fixture
def sent_events(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """攔下 create_item 送出的 WS 事件，並讓 Document 不碰資料庫。"""
    events: list[dict] = []

    async def fake_create(data):
        return {**data, "id": "item-1", "is_disabled": False}

    async def fake_send_to_user(user_id, message):
        events.append(message)

    # 換掉 classmethod 用一般函式即可：service 是以 `ItemTable.create(...)`（經由類別）
    # 取用的，拿到的就是這個函式本身。作法同 test_routes.py 的 find_detail_by_id。
    monkeypatch.setattr(ItemTable, "create", fake_create)
    monkeypatch.setattr(item_service.ws_manager, "send_to_user", fake_send_to_user)

    return events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "expected"),
    [
        (Language.ZH, "已建立項目「示範」"),
        (Language.EN, "Created item “示範”"),
    ],
)
async def test_item_created_message_follows_request_language(sent_events, language, expected):
    token = current_language.set(language)
    try:
        await item_service.create_item(
            form_data=ItemCreate(name="示範", description=""),
            current_user_id="user-1",
        )
    finally:
        current_language.reset(token)

    assert len(sent_events) == 1
    assert sent_events[0]["message"] == expected


@pytest.mark.asyncio
async def test_item_created_message_keeps_the_item_name(sent_events):
    """名稱是插進文案的，不是文案的一部分 —— 換語系不能把它弄丟。"""
    await item_service.create_item(
        form_data=ItemCreate(name="Quarterly report", description=""),
        current_user_id="user-1",
    )

    assert "Quarterly report" in sent_events[0]["message"]
