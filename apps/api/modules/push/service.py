from shared.http.errors import LangText, resolve_text

from .dispatcher import NotificationDispatcher, NotificationPayload
from .model import PushSubscriptionTable
from .schema import AdminBroadcast, RegisterSubscription, SubscriptionOperate

# 測試通知的文案。走 LangText 的理由同 `modules/items/service.py` 的 WS 事件訊息：
# 這是送到使用者眼前的文字。用 `resolve_text()`（這次請求的語系）也是同一個前提 ——
# `/push/test` 只推給呼叫者自己。
TEST_PUSH_TITLE = LangText(zh="推播測試", en="Push test")
TEST_PUSH_BODY = LangText(zh="推播功能正常運作", en="Push notifications are working")


async def upsert_subscription(user_id: str, data: RegisterSubscription) -> SubscriptionOperate:
    existing = await PushSubscriptionTable.find_detail_by_endpoint(data.endpoint)
    subscription_data = {
        "user_id": user_id,
        "endpoint": data.endpoint,
        "p256dh": data.p256dh,
        "auth": data.auth,
        "user_agent": data.user_agent,
    }
    if existing:
        if all(existing.get(key) == value for key, value in subscription_data.items()):
            return SubscriptionOperate(ok=True)
        await PushSubscriptionTable.update_by_id(existing["id"], data=subscription_data)
        return SubscriptionOperate(ok=True)
    await PushSubscriptionTable.create(subscription_data)
    return SubscriptionOperate(ok=True)


async def remove_subscription(user_id: str, endpoint: str) -> SubscriptionOperate:
    # 別人的 endpoint 一律當成「沒有這筆」而不是報錯：endpoint 是瀏覽器給的不透明字串，
    # 回 404／403 等於讓任何登入者拿它探測某個 endpoint 存不存在。
    # 但也**不能謊報成功** —— `ok=False` 讓呼叫端知道自己沒刪掉任何東西。
    existing = await PushSubscriptionTable.find_detail_by_endpoint(endpoint)
    if not existing or existing["user_id"] != user_id:
        return SubscriptionOperate(ok=False)
    await PushSubscriptionTable.delete_by_id(existing["id"])
    return SubscriptionOperate(ok=True)


async def send_test_push(user_id: str) -> SubscriptionOperate:
    payload = NotificationPayload(
        title=resolve_text(TEST_PUSH_TITLE),
        body=resolve_text(TEST_PUSH_BODY),
        url="/",
    )
    await NotificationDispatcher.send_to_user(user_id=user_id, payload=payload)
    return SubscriptionOperate(ok=True)


async def broadcast(data: AdminBroadcast) -> SubscriptionOperate:
    payload = NotificationPayload(title=data.title, body=data.body, url=data.url)
    await NotificationDispatcher.broadcast(payload=payload)
    return SubscriptionOperate(ok=True)
