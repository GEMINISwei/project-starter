"""簡易滑動視窗速率限制。

刻意用行程內記憶體實作, 不引入 Redis (為了限流多一個必要的基礎設施不划算)。代價:
**多個後端副本時各算各的** (N 倍的允許次數), 重啟後歸零。需要跨副本時把 `_hits` 換成
Redis 的 sorted set, `check()`/`reset()`/`clear()` 三個對外介面不用動。
"""

import math
import time
from collections import deque

from fastapi import Request

from .errors import BaseError, LangException, LangText

# 全域清理的最小間隔 (window_seconds 的倍數)。每次都掃會讓被攻擊時最慢的是防護程式碼自己。
_SWEEP_INTERVAL_RATIO = 1.0


class RateLimitError(BaseError):
    TOO_MANY_REQUESTS = LangText(
        zh="嘗試次數過多，請稍後再試",
        en="Too Many Attempts, Please Try Again Later",
    )


class RateLimiter:
    """對同一個 key 在 `window_seconds` 內最多允許 `max_attempts` 次。

    `max_keys` 是**記憶體上限**: 攻擊者可以持續變換 key (例如帳號名), 限流器不能因此吃光記憶體。
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
        # 刻意用普通 dict 而不是 defaultdict: 讀取不該產生條目。
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
        # 先收集再刪除: 不要在迭代 dict 的同時改動它。
        expired = [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]
        for key in expired:
            del self._hits[key]
        self._last_sweep = now

    def _enforce_capacity(self, now: float) -> None:
        """確保 key 數量不超過 `max_keys`。

        先掃掉過期的; 還是滿的話淘汰最久沒活動的那些。刻意**不是**「滿了就拒絕新的 key」:
        那會讓攻擊者用垃圾 key 塞滿表格之後, 把真實使用者擋在外面。
        """
        if len(self._hits) < self.max_keys:
            return

        self._sweep(now)
        if len(self._hits) < self.max_keys:
            return

        # 依最後一次活動時間排序, 砍掉最舊的 10%, 避免每加一個 key 就要排序一次。
        evict_count = max(1, len(self._hits) - self.max_keys + self.max_keys // 10)
        oldest = sorted(self._hits, key=lambda k: self._hits[k][-1])[:evict_count]
        for key in oldest:
            del self._hits[key]

    def check(self, key: str) -> None:
        """記錄一次嘗試; 超過上限時丟出帶 `Retry-After` 的 429。"""
        now = time.monotonic()

        if now - self._last_sweep >= self.window_seconds * _SWEEP_INTERVAL_RATIO:
            self._sweep(now)

        hits = self._prune(key, now)

        if len(hits) >= self.max_attempts:
            # 最舊的那一筆掉出視窗時就有額度。
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
        """成功之後呼叫, 讓正常使用者不會因為之前失敗而被鎖住。"""
        self._hits.pop(key, None)

    def clear(self) -> None:
        """僅供測試使用。"""
        self._hits.clear()
        self._last_sweep = time.monotonic()


def client_ip(request: Request) -> str:
    """取得用戶端 IP, 只適合限流這類盡力而為的防護, 不能拿來做授權判斷。

    `request.client.host` 永遠是 web 容器 (瀏覽器 → nginx → Next → 這裡)。nginx 以
    `$remote_addr` **覆寫** `X-Real-IP`, Next 再原樣轉傳 (`apps/web/shared/api/headers.ts`) ——
    **少了任何一段, 全站就共用同一個限流 key**。不要讀 `X-Forwarded-For`, 它可由用戶端偽造。
    """
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    # 沒有經過 nginx (例如直接打 api:8000、或測試環境) 時的退路。
    return request.client.host if request.client else "unknown"
