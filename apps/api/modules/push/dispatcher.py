import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from typing import Protocol

from pywebpush import WebPushException, webpush

from .model import PushSubscriptionDetail, PushSubscriptionTable

logger = logging.getLogger(__name__)


class PushConfig(Protocol):
    vapid_private_key: str
    vapid_subject: str


_config: PushConfig | None = None


def configure_push(config: PushConfig) -> None:
    global _config
    _config = config


@dataclass
class NotificationPayload:
    title: str
    body: str
    url: str = "/"


class NotificationDispatcher:
    @classmethod
    def _is_enabled(cls) -> bool:
        """VAPID 金鑰沒設定就代表沒啟用 Web Push（見 app/config.py）。

        少了這道檢查，未設定 VAPID 的部署每次通知都會帶著空金鑰呼叫 webpush、失敗、
        再往 log 噴一則 error —— 明明是「功能沒開」，看起來卻像是壞掉了。
        """
        return bool(_config and _config.vapid_private_key)

    @classmethod
    async def send_to_user(cls, user_id: str, payload: NotificationPayload) -> None:
        if not cls._is_enabled():
            logger.debug("Web Push 未設定 VAPID 金鑰，略過對 user %s 的推播", user_id)
            return

        subscriptions = await PushSubscriptionTable.find_details_by_user_id(user_id)
        logger.debug("Sending push to user %s (%d subscriptions)", user_id, len(subscriptions))
        for sub in subscriptions:
            await cls._deliver(sub, payload)

    @classmethod
    async def broadcast(cls, payload: NotificationPayload) -> None:
        """推播給所有訂閱者。

        逐一送出而非並發：Web Push 端點分散在各家推播服務，突然打出大量並發請求容易
        被限流。模版的使用情境（數百個訂閱）循序送完全足夠；真的要擴大規模時，
        建議改成背景工作佇列，而不是在請求裡開一堆並發。
        """
        if not cls._is_enabled():
            logger.debug("Web Push 未設定 VAPID 金鑰，略過廣播")
            return

        subscriptions = await PushSubscriptionTable.find_all_details()
        logger.info("Broadcasting push to %d subscriptions", len(subscriptions))
        for sub in subscriptions:
            await cls._deliver(sub, payload)

    @classmethod
    async def _deliver(
        cls,
        subscription: PushSubscriptionDetail,
        payload: NotificationPayload,
    ) -> None:
        if _config is None:
            return
        try:
            await asyncio.to_thread(
                webpush,
                subscription_info={
                    "endpoint": subscription["endpoint"],
                    "keys": {
                        "p256dh": subscription["p256dh"],
                        "auth": subscription["auth"],
                    },
                },
                data=json.dumps(asdict(payload)),
                vapid_private_key=_config.vapid_private_key,
                vapid_claims={"sub": _config.vapid_subject},
            )
            logger.debug("Push delivered to endpoint %s", subscription["endpoint"])
        except WebPushException as e:
            if e.response and e.response.status_code in (404, 410):
                await PushSubscriptionTable.delete_by_id(subscription["id"])
            else:
                logger.error("WebPushException for endpoint %s: %s", subscription["endpoint"], e)
        except Exception as e:
            logger.error("Unexpected error delivering push to %s: %s", subscription["endpoint"], e)
