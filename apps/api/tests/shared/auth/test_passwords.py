"""bcrypt 必須離開 event loop 的執行緒 (見 `shared/auth/passwords.py`)。

為什麼值得專門測: bcrypt 是刻意設計成慢的, 預設成本下一次雜湊約 100–300ms, 而且是純
CPU 工作。在 async 函式裡直接呼叫, 等於在這段時間內把整個 event loop 停住 —— 不是
「這個請求變慢」, 是**所有**請求都停住。後端是單一 uvicorn worker, 所以這條的影響是
「登入吞吐量的硬上限」加上「任何人都能靠連打登入端點讓服務失去回應」。

這種退化不會有任何既有測試自然抓到: 功能完全正常, 只是併發時全部排隊。所以要明確斷言
「雜湊發生在別的執行緒」。
"""

import asyncio
import threading

import pytest

from shared.auth import passwords
from shared.auth.passwords import hash_password_async, verify_login_password, verify_password_async


@pytest.mark.asyncio
async def test_hash_password_runs_off_the_event_loop_thread(monkeypatch: pytest.MonkeyPatch):
    """真正的斷言不是「有沒有算出雜湊」, 而是「在哪個執行緒算的」。"""
    loop_thread = threading.get_ident()
    recorded: list[int] = []

    real_hash = passwords.hash_password

    def recording_hash(raw_password: str) -> str:
        recorded.append(threading.get_ident())
        return real_hash(raw_password)

    monkeypatch.setattr(passwords, "hash_password", recording_hash)

    result = await hash_password_async("some-password")

    assert result.startswith("$2b$")
    assert recorded, "hash_password 沒有被呼叫到，這個測試沒有測到東西"
    assert recorded[0] != loop_thread


@pytest.mark.asyncio
async def test_verify_password_runs_off_the_event_loop_thread(monkeypatch: pytest.MonkeyPatch):
    loop_thread = threading.get_ident()
    hashed = await hash_password_async("some-password")

    recorded: list[int] = []
    real_verify = passwords.verify_password

    def recording_verify(plain_password: str, hashed_password: str) -> bool:
        recorded.append(threading.get_ident())
        return real_verify(plain_password, hashed_password)

    monkeypatch.setattr(passwords, "verify_password", recording_verify)

    assert await verify_password_async("some-password", hashed) is True
    assert recorded, "verify_password 沒有被呼叫到，這個測試沒有測到東西"
    assert recorded[0] != loop_thread


@pytest.mark.asyncio
async def test_verify_rejects_wrong_password():
    hashed = await hash_password_async("correct")

    assert await verify_password_async("wrong", hashed) is False


@pytest.mark.asyncio
async def test_event_loop_stays_responsive_during_hashing():
    """行為面的證據: 雜湊進行中, event loop 仍然可以推進其他工作。

    同步版本會讓下面的 ticker 在整個雜湊期間一次都跑不動。這條比「檢查執行緒 id」更貼近
    我們真正在意的事 —— 服務在有人登入時還能不能回應別人。
    """
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            ticks += 1
            await asyncio.sleep(0.001)

    task = asyncio.create_task(ticker())
    try:
        await hash_password_async("some-password")
    finally:
        task.cancel()

    # bcrypt 至少要 100ms 上下, 1ms 一次的 ticker 期間應該推進很多次。
    # 門檻刻意設得很寬鬆 (只要求 > 5), 避免在慢機器或 CI 上變成 flaky。
    assert ticks > 5


@pytest.mark.asyncio
async def test_login_check_still_hashes_when_the_account_does_not_exist(
    monkeypatch: pytest.MonkeyPatch,
):
    """帳號不存在時也要真的比對一次, 否則回應時間洩漏帳號是否存在。"""
    calls: list[str] = []
    real_verify = passwords.verify_password

    def recording_verify(plain_password: str, hashed_password: str) -> bool:
        calls.append(hashed_password)
        return real_verify(plain_password, hashed_password)

    monkeypatch.setattr(passwords, "verify_password", recording_verify)

    assert await verify_login_password("dummy-password", None) is False
    assert len(calls) == 1
