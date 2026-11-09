"""HTTP 以外的入口沒有自己開 session 時, 要得到說明怎麼修的錯誤。

而不是在某個 `None.execute` 上炸出看不出原因的 AttributeError。
"""

import pytest

from shared.db.session import active_session


def test_active_session_outside_scope_raises_with_guidance():
    with pytest.raises(RuntimeError, match="session_scope"):
        active_session()
