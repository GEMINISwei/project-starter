"""**範例模組**的商業邏輯。用不到時整包刪除，見 docs/architecture.md「移除 module」。

除了一般的 CRUD，這裡也示範**怎麼送出 WebSocket 事件**（見 `create_item`）——
模板的 WS 機制本身是通用的，但沒有範例的話，第一次要用的人得自己從
`modules/realtime/schema.py` 與 `modules/realtime/manager.py` 拼出用法。

**參數慣例（新模組請照抄）**：id 直接當具名參數傳，表單資料傳 `schema.py` 的 Pydantic
model 本身。這讓 schema 欄位變更能由型別檢查捕捉，而不是在執行期才出錯。
"""

import logging
from typing import Literal

from modules.realtime.public import WsEvent, WsEventType, ws_manager
from shared.db.table import resolve_disabled_at
from shared.http.errors import BaseError, LangText, ensure_found, resolve_text

from .model import ItemTable
from .schema import ItemCreate, ItemInfo, ItemList, ItemOperate, ItemUpdate

logger = logging.getLogger(__name__)


class ItemError(BaseError):
    NOT_FOUND = LangText(zh="項目不存在", en="Item Not Found")


# WS 事件的文案。**送到使用者眼前的文字一律走 LangText**，即使它不是錯誤 —— 少了這一步，英文
# 使用者會收到一則中文 toast，而前端的 fallback 永遠用不到（後端一給 message 它就是死碼）。
#
# 這裡可以用 `resolve_text()`（取**這次請求**的語系），因為下面是 `send_to_user(current_user_id,
# ...)`，收件人就是發起請求的人。**廣播事件不能這樣做**：收件人各有各的語系，而事件只組一次 ——
# 要嘛內容是管理者自己打的字（如 SYSTEM_ANNOUNCEMENT），要嘛只帶 type + id 讓前端自己組。
ITEM_CREATED_MESSAGE = LangText(zh="已建立項目「{name}」", en="Created item “{name}”")


async def create_item(form_data: ItemCreate, current_user_id: str) -> ItemOperate:
    created = await ItemTable.create(
        data={**form_data.model_dump(), "created_by_id": current_user_id}
    )

    # 通知失敗不能讓「建立成功」被回滾成錯誤 —— 資料已經寫進去了，記下來就好。
    try:
        event = WsEvent(
            type=WsEventType.ITEM_CREATED,
            message=resolve_text(ITEM_CREATED_MESSAGE).format(name=created["name"]),
        )
        await ws_manager.send_to_user(current_user_id, event.model_dump(mode="json"))
    except Exception:
        logger.warning("item ws notification failed", exc_info=True)

    return ItemOperate.model_validate(created)


async def get_item(id: str) -> ItemInfo:
    return ItemInfo.model_validate(
        ensure_found(await ItemTable.find_detail_by_id(id), ItemError.NOT_FOUND)
    )


async def get_item_list(
    limit: int,
    cursor: str | None = None,
    direction: Literal["next", "prev"] = "next",
    name: str | None = None,
    is_disabled: bool | None = None,
) -> ItemList:
    return ItemList.model_validate(
        await ItemTable.find_list(
            cursor=cursor,
            direction=direction,
            limit=limit,
            name=name,
            is_disabled=is_disabled,
        )
    )


async def update_item(id: str, form_data: ItemUpdate) -> ItemOperate:
    item = ensure_found(await ItemTable.find_detail_by_id(id), ItemError.NOT_FOUND)

    # 再包一次 ensure_found：查到之後、更新之前文件仍可能被刪掉，少了它那個競態會變成 500。
    updated = ensure_found(
        await ItemTable.update_by_id(
            id=id,
            data={
                "name": form_data.name,
                "description": form_data.description,
                "is_disabled": form_data.is_disabled,
                # 停用時間交給共用 helper 決定，各模組才不會各寫一套語義。
                "disabled_at": resolve_disabled_at(item.get("disabled_at"), form_data.is_disabled),
            },
        ),
        ItemError.NOT_FOUND,
    )

    return ItemOperate.model_validate(updated)


async def delete_item(id: str) -> ItemOperate:
    ensure_found(await ItemTable.find_detail_by_id(id), ItemError.NOT_FOUND)

    return ItemOperate.model_validate(
        ensure_found(await ItemTable.delete_by_id(id=id), ItemError.NOT_FOUND)
    )
