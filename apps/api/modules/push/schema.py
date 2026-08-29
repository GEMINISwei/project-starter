from pydantic import BaseModel

from shared.http.schema import NonEmptyText


class RegisterSubscription(BaseModel):
    endpoint: NonEmptyText
    p256dh: NonEmptyText
    auth: NonEmptyText
    user_agent: str | None = None



class AdminBroadcast(BaseModel):
    title: NonEmptyText
    body: NonEmptyText
    url: str = "/"


class SubscriptionOperate(BaseModel):
    """操作結果。`ok=false` 代表請求合法但沒有造成任何改變（例如要退訂的 endpoint 不是你的）。"""

    ok: bool


class VapidKey(BaseModel):
    public_key: str
