import os
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete

from shared.db.session import configure_session_factory, create_engine, session_scope
from shared.db.table import BaseTable
from tests.integration import require_postgres


@pytest.fixture(autouse=True)
def mock_app_env(monkeypatch: pytest.MonkeyPatch):
    """換掉 app.state.env, 讓 API 測試不必依賴 .env 檔。"""
    from app.server import app

    mock_env = MagicMock()
    mock_env.expire_hours = 8
    mock_env.project_name = "sample-test"
    mock_env.token_version = "1"
    # 至少 32 bytes, 理由同 tests/shared/auth/test_tokens.py 的 MockEnv。
    mock_env.jwt_secret_key = "test_secret_key_for_api_test_at_least_32_chars"
    mock_env.jwt_algorithm = "HS256"
    mock_env.register_key = ""

    monkeypatch.setattr(app.state, "env", mock_env)


@pytest_asyncio.fixture
async def client():
    from app.server import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
def set_current_users():
    """回傳一個 setter: 傳入 {username: user_dict} 覆寫 current_user_resolver。

    測試結束後自動還原。
    """
    from app.server import app

    original_resolver = app.state.current_user_resolver

    def _set(users: dict):
        # `username` 與 `auth_version` 由這裡補: 兩者都是 `CurrentUser` 的必填欄位
        # (來自 TokenSubject), 真正的 resolver 一定會提供。少補的話, 任何讀
        # `current_user["username"]` 的程式碼在測試裡會是 KeyError → 500,
        # 而在正式環境完全正常 —— 那種差異會讓測試對「這條路徑會不會壞」說謊。
        users = {
            username: {"auth_version": 1, "username": username, **user}
            for username, user in users.items()
        }

        async def resolver(username: str):
            return users.get(username)

        app.state.current_user_resolver = resolver

    yield _set
    app.state.current_user_resolver = original_resolver


@pytest_asyncio.fixture
async def db():
    """連上真的 PostgreSQL、建好正式 model 的資料表並清空; 沒有可用的資料庫就跳過。

    給各模組的 `test_model.py` (integration) 用。連線邏輯與 `tests/shared/db/conftest.py` 的
    `_connect` 相同, 但那一份綁死在 shared 自己的測試資料表上 (刻意的, 見該檔說明)。

    **不點名任何模組的資料表**: 清空走 metadata 的外鍵排序, 所以刪掉一個模組時這裡不必改,
    也不會因為 import 不到已刪除的 model 而讓整批測試在 collection 階段失敗。
    """
    url = os.environ["POSTGRES_URL"]
    engine = create_engine(url)
    await require_postgres(engine, url)

    async with engine.begin() as connection:
        # 整份 metadata 一起建: 正式 model 之間有外鍵 (user_roles → roles), 只挑其中幾張
        # 會建不起來。測試資料庫從 metadata 直接建、不跑 migration —— 這不是第二條建表路徑:
        # `make check integration` 用 `alembic check` 保證兩者等價, 而這條快得多。
        await connection.run_sync(BaseTable.metadata.create_all)
        await _truncate(connection)

    configure_session_factory(engine)
    try:
        async with session_scope():
            yield
    finally:
        async with engine.begin() as connection:
            await _truncate(connection)
        await engine.dispose()


async def _truncate(connection) -> None:
    # 反過來的外鍵順序: 先刪參照別人的表, 被參照的最後刪。
    for table in reversed(BaseTable.metadata.sorted_tables):
        await connection.execute(delete(table))
