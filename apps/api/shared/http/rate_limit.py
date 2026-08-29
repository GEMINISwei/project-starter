"""簡易滑動視窗速率限制。

刻意用行程內記憶體實作，不引入 Redis：這是一個要能 `make dev` 就跑起來的模版，為了限流
就多一個必要的基礎設施並不划算。代價要講清楚 ——

- **多個後端副本時，限制是各算各的**（N 個副本 = N 倍的允許次數）。
- 重啟後計數歸零。

對「擋住暴力猜密碼／猜邀請碼」這個目的來說，這樣已經能把嘗試速率壓到無法窮舉的程度。
真的需要跨副本的精確限流時，把 `_Counter` 換成 Redis 實作即可，`RateLimiter` 的介面不用動。
"""

import math
import time
from collections import deque

from fastapi import Request

from .errors import BaseError, LangException, LangText

# 全域清理的最小間隔（相對於 window_seconds 的倍數）。
#
# 每次 check() 都掃過整個 dict 會讓限流本身變成 O(keys)，被攻擊時最慢的路徑反而是防護程式碼
# 自己。間隔設成一個視窗長度：過期的 key 最多多存活一個視窗，攤提下來每個 key 只掃到常數次。
_SWEEP_INTERVAL_RATIO = 1.0


class RateLimitError(BaseError):
    TOO_MANY_REQUESTS = LangText(
        zh="嘗試次數過多，請稍後再試",
        en="Too Many Attempts, Please Try Again Later",
    )


class RateLimiter:
    """對同一個 key 在 `window_seconds` 內最多允許 `max_attempts` 次。

    `max_keys` 是**記憶體上限**，不是業務參數。登入的 key 是 `ip:username`，因此攻擊者可
    持續變換帳號名；限流器必須限制追蹤的 key 數量，避免本身成為記憶體耗盡的攻擊面。
    """

    def __init__(self, max_attempts: int, window_seconds: float, max_keys: int = 50_000) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts 必須至少為 1")
        if window_seconds <= 0:
            raise ValueError("window_seconds 必須大於 0")
        if max_keys < 1:
            raise ValueError("max_keys 必須至少為 1")

        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.max_keys = max_keys
        # 刻意用普通 dict 而不是 defaultdict：讀取不該產生條目。
        self._hits: dict[str, deque[float]] = {}
        self._last_sweep = time.monotonic()

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits.get(key)
        if hits is None:
            return deque()

        cutoff = now - self.window_seconds
        while hits and hits[0] <= cutoff:
            hits.popleft()
        return hits

    def _sweep(self, now: float) -> None:
        """移除所有已經完全過期的 key。"""
        cutoff = now - self.window_seconds
        # 先收集再刪除：不要在迭代 dict 的同時改動它。
        expired = [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in expired:
            del self._hits[key]
        self._last_sweep = now

    def _enforce_capacity(self, now: float) -> None:
        """確保 key 數量不超過 `max_keys`。

        先掃掉過期的；如果掃完還是滿的（代表正在被大量不同 key 灌），就淘汰
        「最後一次活動時間最舊」的那些 —— 它們本來就最接近過期。

        刻意**不是**「滿了就拒絕新的 key」：那會讓攻擊者用垃圾 key 塞滿表格之後，
        把真實使用者擋在限流器外面（或反過來讓真實使用者全部吃 429），
        等於把記憶體問題換成一個更糟的可用性問題。
        """
        if len(self._hits) < self.max_keys:
            return

        self._sweep(now)
        if len(self._hits) < self.max_keys:
            return

        # 依最後一次活動時間排序，砍掉最舊的 10%，避免每加一個 key 就要排序一次。
        evict_count = max(1, len(self._hits) - self.max_keys + self.max_keys // 10)
        oldest = sorted(self._hits, key=lambda k: self._hits[k][-1])[:evict_count]
        for key in oldest:
            del self._hits[key]

    def check(self, key: str) -> None:
        """記錄一次嘗試；超過上限時丟出帶 `Retry-After` 的 429。"""
        now = time.monotonic()

        if now - self._last_sweep >= self.window_seconds * _SWEEP_INTERVAL_RATIO:
            self._sweep(now)

        hits = self._prune(key, now)

        if len(hits) >= self.max_attempts:
            # 最舊的那一筆掉出視窗時就會有額度，`Retry-After` 用它算 —— 沒有這個標頭，用戶端
            # 只能靠猜的重試，而猜錯的代價是再吃一次 429。
            retry_after = max(1, math.ceil(hits[0] + self.window_seconds - now))
            raise LangException(
                429,
                RateLimitError.TOO_MANY_REQUESTS,
                headers={"Retry-After": str(retry_after)},
            )

        if key not in self._hits:
            self._enforce_capacity(now)
            self._hits[key] = hits

        hits.append(now)

    def reset(self, key: str) -> None:
        """成功之後呼叫，讓正常使用者不會因為之前失敗而被鎖住。"""
        self._hits.pop(key, None)

    def clear(self) -> None:
        """僅供測試使用。"""
        self._hits.clear()
        self._last_sweep = time.monotonic()


def client_ip(request: Request) -> str:
    """取得用戶端 IP。

    優先看 `X-Real-IP`，因為 `request.client.host` **不是**用戶端位址。

    **這條路徑上有兩跳，兩跳都不是瀏覽器直連。** 用到限流的兩條端點（登入、註冊）都由
    Server Action 呼叫，也就是：瀏覽器 → nginx → Next 伺服器端 → 這裡。nginx 以
    `$remote_addr` **覆寫** `X-Real-IP`（用戶端送什麼都會被蓋掉），Next 再原樣往下轉傳
    （`apps/web/shared/api/headers.ts` 的 `clientIp`）。因此 `request.client.host`
    永遠是 web 那個容器 —— **少了任何一段轉傳，全站所有人就共用同一個限流 key**。

    **不要讀 `X-Forwarded-For`。** 它可由用戶端偽造或累加，不能作為限流 key 的可信來源。

    仍然只適合用來做限流這類「盡力而為」的防護，不能拿來做授權判斷：這個保證的前提是
    「nginx 是最外層，且它的設定沒被改壞」，而那是部署層的事實，不是密碼學上的證明。
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    # 沒有經過 nginx（例如直接打 api:8000、或測試環境）時的退路。
    return request.client.host if request.client else "unknown"
