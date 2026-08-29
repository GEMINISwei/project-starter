from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest.fixture(autouse=True)
def mock_app_env(monkeypatch: pytest.MonkeyPatch):
    """換掉 app.state.env，讓 API 測試不必依賴 .env 檔。"""
    from app.server import app

    mock_env = MagicMock()
    mock_env.expire_hours = 8
    mock_env.project_name = "sample-test"
    mock_env.token_version = "1"
    # 至少 32 bytes，理由同 tests/shared/test_auth.py 的 MockEnv。
    mock_env.jwt_secret_key = "test_secret_key_for_api_test_at_least_32_chars"
    mock_env.jwt_algorithm = "HS256"
    mock_env.register_key = ""
    mock_env.vapid_public_key = ""

    monkeypatch.setattr(app.state, "env", mock_env)


@pytest_asyncio.fixture
async def client():
    from app.server import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
def set_current_users():
    """回傳一個 setter：傳入 {username: user_dict} 覆寫 current_user_resolver。

    測試結束後自動還原。
    """
    from app.server import app

    original_resolver = app.state.current_user_resolver

    def _set(users: dict):
        users = {username: {"auth_version": 1, **user} for username, user in users.items()}

        async def resolver(username: str):
            return users.get(username)

        app.state.current_user_resolver = resolver

    yield _set
    app.state.current_user_resolver = original_resolver
