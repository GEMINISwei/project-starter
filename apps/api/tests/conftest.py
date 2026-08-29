"""測試用的最小環境變數。

`app.config` 的必填欄位（PROJECT_NAME / POSTGRES_URL / JWT_SECRET_KEY）在 import 當下就會
驗證，所以要在任何 `app.*` 被 import 之前設好。pytest 會先載入 conftest.py，因此這裡是
最早、也是唯一需要處理的地方。
"""

import os

import pytest

os.environ.setdefault("PROJECT_NAME", "sample-test")
os.environ.setdefault(
    "POSTGRES_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres",
)
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_for_api_test_at_least_32_chars")
os.environ.setdefault("MODE", "development")


@pytest.fixture(autouse=True, scope="session")
def _default_session_factory():
    """替整批測試安裝一個預設的 session factory。

    `app/server.py` 的 middleware 每個請求都會開一個 session，但 ASGITransport 不會跑
    lifespan，所以沒有人安裝 factory —— 少了這個 fixture，**每一條路由測試**都會在
    middleware 就撞上「session factory 尚未安裝」。

    這裡不需要資料庫真的活著：建立引擎不會連線，而把 model 都 stub 掉的路由測試
    自始至終不會發出任何查詢，那個 session 也就永遠不會去要連線。
    真的要碰資料庫的測試各自用 `require_postgres` 換上自己的引擎。
    """
    from shared.db.session import configure_session_factory, create_engine

    configure_session_factory(create_engine(os.environ["POSTGRES_URL"]))
