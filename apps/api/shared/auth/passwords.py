"""密碼雜湊 (bcrypt)。

與任何業務無關: 哪個 module 擁有帳號資料都一樣要用, 所以住在 shared, 新專案自己寫帳號
模組時直接拿去用。

**請求路徑上一律用 `*_async` 版本。** bcrypt 一次約 100–300ms 的純 CPU 工作, 直接在 async
函式裡呼叫會停住**所有**請求; 丟到執行緒池 (bcrypt 會釋放 GIL, 所以是真的平行)。
"""

import asyncio

import bcrypt

#: bcrypt 的硬限制: 超過的位元組會被**靜默截斷**, 不是我們挑的數字。schema 的密碼欄位要擋。
MAX_PASSWORD_BYTES = 72


def hash_password(raw_password: str) -> str:
    """**同步**版本, 只給模組載入時建立 dummy hash 與測試用。"""
    return bcrypt.hashpw(raw_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """**同步**版本。請求路徑上一律用 `verify_password_async`。"""
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


async def hash_password_async(raw_password: str) -> str:
    return await asyncio.to_thread(hash_password, raw_password)


async def verify_password_async(plain_password: str, hashed_password: str) -> bool:
    return await asyncio.to_thread(verify_password, plain_password, hashed_password)


_DUMMY_PASSWORD_HASH = hash_password("dummy-password")


async def verify_login_password(plain_password: str, hashed_password: str | None) -> bool:
    """登入用的比對: 帳號不存在 (`hashed_password` 是 None) 時也比對一次 dummy hash。

    否則回應時間本身就洩漏了帳號是否存在 —— 不存在的帳號會快上一個 bcrypt 的時間。
    帳號不存在時一律回傳 False。
    """
    matched = await verify_password_async(plain_password, hashed_password or _DUMMY_PASSWORD_HASH)
    return matched and hashed_password is not None
