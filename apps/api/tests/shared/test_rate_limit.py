from types import SimpleNamespace

import pytest

from shared.http.errors import LangException
from shared.http.rate_limit import RateLimiter, client_ip


def _request(headers: dict[str, str], client_host: str | None = "10.0.0.1"):
    """最小的假 Request：`client_ip()` 只用到 `.headers` 與 `.client`。

    Starlette 的 header 查詢是大小寫不敏感的，所以這裡用小寫 key 建表、
    查詢時也用小寫，行為與正牌一致。
    """
    return SimpleNamespace(
        headers={k.lower(): v for k, v in headers.items()},
        client=SimpleNamespace(host=client_host) if client_host else None,
    )


def test_allows_up_to_the_limit():
    limiter = RateLimiter(max_attempts=3, window_seconds=60)

    for _ in range(3):
        limiter.check("ip-1")


def test_blocks_beyond_the_limit_with_429():
    limiter = RateLimiter(max_attempts=3, window_seconds=60)
    for _ in range(3):
        limiter.check("ip-1")

    with pytest.raises(LangException) as exc_info:
        limiter.check("ip-1")

    assert exc_info.value.status_code == 429


def test_keys_are_counted_independently():
    """一個人被限流不該影響到別人 —— 否則就變成阻斷服務的手段。"""
    limiter = RateLimiter(max_attempts=2, window_seconds=60)
    limiter.check("ip-1")
    limiter.check("ip-1")

    limiter.check("ip-2")  # 不同 key，不受影響


def test_reset_clears_the_counter():
    """成功登入後呼叫 reset，正常使用者不會因為之前打錯幾次就被卡住。"""
    limiter = RateLimiter(max_attempts=2, window_seconds=60)
    limiter.check("ip-1")
    limiter.check("ip-1")

    limiter.reset("ip-1")

    limiter.check("ip-1")


def test_window_slides_so_old_attempts_expire():
    """視窗是滑動的：舊的嘗試過期之後應該重新放行。"""
    # 用極短的視窗代替 sleep，避免測試變慢。
    limiter = RateLimiter(max_attempts=1, window_seconds=0.05)
    limiter.check("ip-1")

    with pytest.raises(LangException):
        limiter.check("ip-1")

    import time

    time.sleep(0.06)
    limiter.check("ip-1")  # 視窗已滑過，重新放行


@pytest.mark.parametrize(
    ("max_attempts", "window_seconds"),
    [(0, 60), (-1, 60), (1, 0), (1, -5)],
)
def test_rejects_nonsensical_configuration(max_attempts, window_seconds):
    with pytest.raises(ValueError):
        RateLimiter(max_attempts=max_attempts, window_seconds=window_seconds)


def test_rejects_nonsensical_max_keys():
    with pytest.raises(ValueError):
        RateLimiter(max_attempts=1, window_seconds=60, max_keys=0)


# --- Retry-After ---------------------------------------------------------


def test_429_carries_retry_after():
    """沒有 Retry-After 的話，用戶端只能靠猜的重試，而猜錯的代價是再吃一次 429。"""
    limiter = RateLimiter(max_attempts=1, window_seconds=60)
    limiter.check("ip-1")

    with pytest.raises(LangException) as exc_info:
        limiter.check("ip-1")

    headers = exc_info.value.headers or {}
    assert "Retry-After" in headers
    # 最舊的一筆剛剛才記錄，所以還要等接近一整個視窗。
    assert 1 <= int(headers["Retry-After"]) <= 60


def test_retry_after_shrinks_as_the_window_slides():
    """視窗過了一半時，Retry-After 應該跟著變短，而不是永遠回報整個視窗長度。"""
    limiter = RateLimiter(max_attempts=1, window_seconds=10)
    limiter.check("ip-1")

    # 手動把那一筆嘗試的時間往前推 8 秒，等同於「已經過了 8 秒」。
    limiter._hits["ip-1"][0] -= 8

    with pytest.raises(LangException) as exc_info:
        limiter.check("ip-1")

    assert int((exc_info.value.headers or {})["Retry-After"]) <= 2


# --- 記憶體上限 ------------------------------------------------------------
#
# 這一組守的是「限流器本身不能變成攻擊面」：登入的 key 是 `ip:username`，單一 IP 換
# 帳號名一直打就能讓追蹤條目持續增加。


def test_reading_an_unknown_key_does_not_create_an_entry():
    """這是 defaultdict 版本最直接的症狀：光是查詢就會長出條目。"""
    limiter = RateLimiter(max_attempts=3, window_seconds=60)

    limiter._prune("never-seen", 0.0)

    assert "never-seen" not in limiter._hits


def test_expired_keys_are_swept():
    """過期的 key 要被真的移除，而不是留著一個空 deque 佔位。"""
    limiter = RateLimiter(max_attempts=5, window_seconds=0.05)
    for i in range(10):
        limiter.check(f"ip-{i}")

    assert len(limiter._hits) == 10

    import time

    time.sleep(0.06)
    # 全域清理是在 check() 裡攤提執行的，所以要有一次新的請求來觸發。
    limiter.check("ip-new")

    assert len(limiter._hits) == 1
    assert set(limiter._hits) == {"ip-new"}


def test_key_count_never_exceeds_max_keys():
    """即使所有 key 都還在視窗內，也不能無限成長。"""
    limiter = RateLimiter(max_attempts=5, window_seconds=3600, max_keys=50)

    for i in range(500):
        limiter.check(f"ip-{i}")

    assert len(limiter._hits) <= 50


def test_capacity_eviction_keeps_the_most_recent_keys():
    """滿了要淘汰最舊的，不是拒絕新的。

    「滿了就拒絕新 key」會讓攻擊者用垃圾 key 塞滿表格之後，把真實使用者擋在限流器外面，
    等於把記憶體問題換成一個更糟的可用性問題。
    """
    limiter = RateLimiter(max_attempts=5, window_seconds=3600, max_keys=20)

    for i in range(100):
        limiter.check(f"ip-{i}")

    # 最後進來的一定還在；最早進來的一定已經被淘汰。
    assert "ip-99" in limiter._hits
    assert "ip-0" not in limiter._hits


# --- client_ip -----------------------------------------------------------
#
# Nginx 會用 `$remote_addr` 覆寫 X-Real-IP；限流只能信任這個由 proxy 設定的值，不能
# 信任用戶端可自行偽造的 X-Forwarded-For。


def test_client_ip_uses_x_real_ip():
    """X-Real-IP 是 nginx 自己以 $remote_addr 覆寫的，是唯一可信的來源。"""
    assert client_ip(_request({"X-Real-IP": "203.0.113.9"})) == "203.0.113.9"


def test_forged_x_forwarded_for_cannot_change_the_key():
    """偽造的 X-Forwarded-For 不得影響限流 key —— 這是繞過限流的主要手法。"""
    request = _request(
        {
            "X-Real-IP": "203.0.113.9",
            "X-Forwarded-For": "1.2.3.4, 5.6.7.8",
        }
    )

    assert client_ip(request) == "203.0.113.9"


def test_x_forwarded_for_alone_is_ignored():
    """沒有 X-Real-IP 時，也不能退而求其次去信任 X-Forwarded-For。

    那個 header 完全由用戶端控制。寧可全部退回 request.client.host（大家共用一個 key，
    最糟就是誤傷），也不要給攻擊者一個「自己指定限流 key」的開關。
    """
    request = _request({"X-Forwarded-For": "1.2.3.4"}, client_host="10.0.0.1")

    assert client_ip(request) == "10.0.0.1"


def test_client_ip_falls_back_to_peer_address():
    """沒有經過 nginx 時（直接打 api:8000、或測試環境）的退路。"""
    assert client_ip(_request({}, client_host="10.0.0.1")) == "10.0.0.1"


def test_client_ip_without_client_returns_unknown():
    assert client_ip(_request({}, client_host=None)) == "unknown"
