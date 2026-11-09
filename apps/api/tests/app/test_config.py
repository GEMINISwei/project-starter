"""環境變數缺漏時, 服務要在啟動當下停下來, 並說清楚是哪一個。"""

import pytest

from app import config


def test_load_env_with_missing_variable_exits_with_readable_message(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.delenv("JWT_SECRET_KEY")

    with pytest.raises(SystemExit) as exc_info:
        config._load_env()

    assert exc_info.value.code == 1
    stderr = capsys.readouterr().err
    assert "環境變數設定錯誤" in stderr
    assert "JWT_SECRET_KEY" in stderr
