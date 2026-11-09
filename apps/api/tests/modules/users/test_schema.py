"""密碼的長度上限以 bytes 計, 不是字元數。

bcrypt 只看前 72 bytes, 超過的部分被靜靜忽略: 不擋的話, 兩組前 72 bytes 相同的密碼
會被當成同一組。中文一個字 3 bytes, 以字元數計算會讓 25 個中文字的密碼溜過去。
"""

import pytest
from pydantic import TypeAdapter, ValidationError

from modules.users.schema import Password
from shared.auth.passwords import MAX_PASSWORD_BYTES

_password = TypeAdapter(Password)


def test_user_create_with_too_long_password_is_rejected():
    assert _password.validate_python("a" * MAX_PASSWORD_BYTES) == "a" * MAX_PASSWORD_BYTES

    with pytest.raises(ValidationError):
        _password.validate_python("a" * (MAX_PASSWORD_BYTES + 1))
    with pytest.raises(ValidationError):
        _password.validate_python("密" * 25)  # 25 個字元, 75 bytes
