"""釘住語系清單的型別契約。

`Language` 是前後端共用的唯一來源：它經由這個端點進入 OpenAPI，`make gen-types` 產成
前端的字串聯集，`apps/web/shared/i18n/locale.ts` 的 `Locale` 直接從那份型別衍生
（漂移由 `apps/web/tests/shared/i18n/locale.test-d.ts` 在編譯期擋下）。
這裡守住後端這一側：端點必須如實列出每一個 enum 成員 —— 少列一個的話，前端的
`Locale` 會少一個選項，而那不會有任何錯誤訊息，只是某個語言靜靜地不存在。

作法比照 tests/modules/realtime/test_ws_events.py。
"""

import pytest
from httpx import AsyncClient

from app.permissions import Permission
from shared.http.errors import Language

from ..helpers import authenticate

USERS = {
    "member": {
        "id": "user-member",
        "nickname": "Member",
        "role_ids": [],
        # 這個端點只要求「有登入」，所以刻意給一個與語系無關的最小權限。
        "permissions": [Permission.USER_READ],
        "is_disabled": False,
    },
}


@pytest.fixture(autouse=True)
def _current_users(set_current_users):
    set_current_users(USERS)


@pytest.mark.asyncio
async def test_languages_lists_every_language(client: AsyncClient):
    authenticate(client, "member")

    response = await client.get("/api/languages/")

    assert response.status_code == 200
    body = response.json()
    assert {item["value"] for item in body["list_data"]} == {
        language.value for language in Language
    }
    assert body["count"] == len(Language)


@pytest.mark.asyncio
async def test_languages_requires_authentication(client: AsyncClient):
    response = await client.get("/api/languages/")

    assert response.status_code == 401
