"""建立超級管理者的兩條路徑（見 `modules/users/service.py`）。

- `signup_user`：網頁 `/signup`，一個部署只能成功一次。
- `create_super_admin`：CLI（`scripts/db.py create-superuser`），可重複執行，
  但會補上同一個 latch，因此執行後 `/signup` 一律關閉。

測試分成兩部分：
- 不需要資料庫的（金鑰比對、guard 已存在時的拒絕、bootstrap-status 端點）
- 標 `integration` 的（併發只有一個成功、失敗時 guard 一起回滾、CLI 的 latch 補寫）——
  那些要真的交易與唯一約束，所以需要 PostgreSQL。
"""

import asyncio
import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from modules.users import service as user_service
from modules.users.bootstrap_model import SUPER_ADMIN_BOOTSTRAP_KEY, SystemStateTable
from modules.users.service import UserError
from shared.db.session import configure_session_factory, create_engine, session_scope
from shared.http.errors import LangException
from tests.integration import require_postgres, restore_session_factory

REGISTER_KEY = "test-register-key-0123456789abcdef"

SIGNUP_PAYLOAD = {
    "username": "root",
    "password": "sup3r-secret",
    "nickname": "Root",
    "register_key": REGISTER_KEY,
}


# --- 不需要資料庫 ---------------------------------------------------------


@pytest.fixture
def _register_key(monkeypatch: pytest.MonkeyPatch):
    """bootstrap 設定由 app composition 經 request state 注入。"""
    import modules.users.router as user_router
    from app.server import app

    monkeypatch.setattr(app.state.env, "register_key", REGISTER_KEY, raising=False)
    user_router.signup_limiter.clear()
    yield
    user_router.signup_limiter.clear()


@pytest.fixture
def _bootstrap_completed(monkeypatch: pytest.MonkeyPatch):
    async def already_done(key, session=None):
        return True

    monkeypatch.setattr(SystemStateTable, "exists", already_done)


@pytest.fixture
def _bootstrap_pending(monkeypatch: pytest.MonkeyPatch):
    async def not_yet(key, session=None):
        return False

    monkeypatch.setattr(SystemStateTable, "exists", not_yet)


@pytest.mark.asyncio
async def test_signup_rejects_wrong_register_key(
    client: AsyncClient, _register_key, _bootstrap_pending
):
    response = await client.post(
        "/api/users/signup",
        json={**SIGNUP_PAYLOAD, "register_key": "wrong-key"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == UserError.REGISTER_KEY_MISMATCH.value.zh


@pytest.mark.asyncio
async def test_signup_is_disabled_when_register_key_is_empty(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, _bootstrap_pending
):
    """空的 REGISTER_KEY 代表整條路徑停用 —— 而不是「不用填金鑰就能過」。

    這是 `not expected_key` 必須擋在比對**之前**的理由：若順序反過來，
    送一個空的 register_key 就會與空的設定值相等而通過。
    """
    import modules.users.router as user_router
    from app.server import app

    monkeypatch.setattr(app.state.env, "register_key", "", raising=False)
    user_router.signup_limiter.clear()

    response = await client.post("/api/users/signup", json={**SIGNUP_PAYLOAD, "register_key": "x"})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_signup_rejected_once_bootstrap_completed(
    client: AsyncClient, _register_key, _bootstrap_completed
):
    """已初始化的系統，即使拿著正確的 REGISTER_KEY 也不能再建立超級管理者。"""
    response = await client.post("/api/users/signup", json=SIGNUP_PAYLOAD)

    assert response.status_code == 409
    assert response.json()["detail"] == UserError.BOOTSTRAP_ALREADY_COMPLETED.value.zh


@pytest.mark.asyncio
async def test_bootstrap_status_reports_available(
    client: AsyncClient, _register_key, _bootstrap_pending
):
    response = await client.get("/api/users/bootstrap-status")

    assert response.status_code == 200
    assert response.json() == {"available": True}


@pytest.mark.asyncio
async def test_bootstrap_status_reports_unavailable_after_completion(
    client: AsyncClient, _register_key, _bootstrap_completed
):
    response = await client.get("/api/users/bootstrap-status")

    assert response.status_code == 200
    assert response.json() == {"available": False}


@pytest.mark.asyncio
async def test_bootstrap_status_reports_unavailable_without_register_key(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, _bootstrap_pending
):
    from app.server import app

    monkeypatch.setattr(app.state.env, "register_key", "", raising=False)

    response = await client.get("/api/users/bootstrap-status")

    assert response.json() == {"available": False}


@pytest.mark.asyncio
async def test_bootstrap_status_needs_no_authentication(
    client: AsyncClient, _register_key, _bootstrap_pending
):
    """註冊頁在使用者登入之前就要決定顯示什麼，所以這條必須是公開的。"""
    client.cookies.clear()

    response = await client.get("/api/users/bootstrap-status")

    assert response.status_code == 200


# --- 需要真的交易與唯一約束（PostgreSQL） ------------------------------------


@pytest_asyncio.fixture
async def bootstrap_db():
    """連上真的 PostgreSQL 並建好 bootstrap 會用到的三張表，回傳超級管理者角色的 id。

    這一組測試沒辦法用假物件替代：要驗證的正是「唯一約束 + 交易在併發下的行為」，
    而那完全是資料庫提供的保證，mock 掉就什麼都沒測到。

    **fixture 本身不進入 session scope**：併發那條測試需要每個 signup 各有自己的
    session（也就是各自的交易），共用一個的話就退化成同一個交易裡的五次寫入，
    唯一約束根本沒有機會仲裁。要用 session 的測試各自呼叫 `in_session()`。
    """
    from modules.roles.model import RoleTable
    from modules.users.model import UserTable, user_roles

    url = os.environ["POSTGRES_URL"]
    engine = create_engine(url)
    await require_postgres(engine, url, "PostgreSQL")

    from shared.db.table import BaseTable

    async def clear(connection):
        await connection.execute(user_roles.delete())
        await connection.execute(delete(UserTable))
        await connection.execute(delete(SystemStateTable))
        await connection.execute(delete(RoleTable))

    with restore_session_factory():
        async with engine.begin() as connection:
            await connection.run_sync(BaseTable.metadata.create_all)
            await clear(connection)

        configure_session_factory(engine)

        # signup 會去取 seed 出來的系統角色，這裡直接建一個真的（外鍵要求它存在）。
        async with session_scope() as session:
            role = RoleTable(code="super_admin", name="超級管理者", permissions=["*"])
            session.add(role)
            await session.flush()
            role_id = str(role.id)

        yield role_id

        async with engine.begin() as connection:
            await clear(connection)
        await engine.dispose()


@pytest.fixture(autouse=True)
def _fixed_super_admin_role(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):
    """讓 `get_super_admin_role_id()` 回傳 fixture 建好的那個角色。

    不 mock 的話它會走 `ensure_seed()`，而那會把角色的 seed 資料寫進測試資料庫 ——
    測到的就變成 seed 的行為，不是 bootstrap 的行為。
    """
    if "bootstrap_db" not in request.fixturenames:
        return

    from modules.roles.model import RoleTable

    async def role_id():
        return request.getfixturevalue("bootstrap_db")

    monkeypatch.setattr(RoleTable, "get_super_admin_role_id", role_id)


async def count(model) -> int:
    """目前表裡有幾列。開自己的 session，不依賴呼叫端的交易狀態。"""
    async with session_scope() as session:
        return await session.scalar(select(func.count()).select_from(model)) or 0


async def in_session(coroutine_factory):
    """在一個獨立的 session（= 一個獨立的交易）裡跑一段程式。"""
    async with session_scope():
        return await coroutine_factory()


def _signup_form(username: str = "root"):
    from modules.users.schema import SignupRequest

    return SignupRequest(
        username=username,
        password="sup3r-secret",
        nickname="Root",
        register_key=REGISTER_KEY,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_concurrent_bootstrap_allows_exactly_one_winner(bootstrap_db):
    """同時送達的多個 signup，最多只有一個成功。

    這條是唯一鍵存在的理由。若改成「先查有沒有超級管理者，沒有就建立」，
    兩個併發請求都會查到「沒有」，然後**都成功** —— 而症狀是多出一個超級管理者，
    幾乎不會有人發現。
    """
    from modules.users.model import UserTable

    def attempt(index: int):
        # 每個 signup 各開一個 session —— 也就是各自一個交易，唯一約束才有仲裁的機會。
        return in_session(
            lambda: user_service.signup_user(
                form_data=_signup_form(f"root-{index}"),
                expected_key=REGISTER_KEY,
            )
        )

    results = await asyncio.gather(
        *[attempt(index) for index in range(5)],
        return_exceptions=True,
    )

    succeeded = [result for result in results if not isinstance(result, BaseException)]
    assert len(succeeded) == 1

    assert await count(UserTable) == 1
    assert await count(SystemStateTable) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_guard_rolls_back_when_user_creation_fails(
    bootstrap_db, monkeypatch: pytest.MonkeyPatch
):
    """使用者建立失敗時，guard 必須跟著回滾。

    否則會落到最糟的狀態：bootstrap 被永久標記為完成，但一個超級管理者都沒有 ——
    沒有人能登入，也沒有任何辦法再跑一次初始化。
    """
    from modules.users.model import UserTable

    async def explode(*args, **kwargs):
        raise RuntimeError("模擬使用者建立失敗")

    monkeypatch.setattr(UserTable, "create", explode)

    with pytest.raises(RuntimeError):
        await in_session(
            lambda: user_service.signup_user(
                form_data=_signup_form(),
                expected_key=REGISTER_KEY,
            )
        )

    assert await count(SystemStateTable) == 0
    # guard 回滾了，所以還能重新初始化。
    assert await in_session(lambda: user_service.bootstrap_available(REGISTER_KEY)) is True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_second_bootstrap_is_rejected(bootstrap_db):
    await in_session(
        lambda: user_service.signup_user(
            form_data=_signup_form("first"),
            expected_key=REGISTER_KEY,
        )
    )

    with pytest.raises(Exception) as exc_info:
        await in_session(
            lambda: user_service.signup_user(
                form_data=_signup_form("second"),
                expected_key=REGISTER_KEY,
            )
        )

    assert getattr(exc_info.value, "status_code", None) == 409
    assert await in_session(lambda: user_service.bootstrap_available(REGISTER_KEY)) is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_new_super_admin_gets_auth_version_one(bootstrap_db):
    """新建立的超級管理者要有 auth_version，否則第一次重設密碼的 +1 會從缺值開始。"""
    from modules.users.model import UserTable

    created = await in_session(
        lambda: user_service.signup_user(
            form_data=_signup_form(),
            expected_key=REGISTER_KEY,
        )
    )

    async with session_scope():
        row = await UserTable.find_by_id(created.id)
        assert row is not None
        assert row.auth_version == 1


# --- CLI 建立超級管理者（scripts/db.py create-superuser） -------------------


def _super_admin_form(username: str = "rescue"):
    from modules.users.schema import SuperAdminCreate

    return SuperAdminCreate(
        username=username,
        password="sup3r-secret",
        nickname="Rescue",
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cli_create_super_admin_closes_signup(bootstrap_db):
    """CLI 建立第一個超級管理者時必須補上 latch。

    少了這一步，用 CLI 完成初始化的部署會把 `/signup` 一直開著 —— 一條公開、未登入、
    能造出全權限帳號的路徑，而且沒有人會注意到它還開著。
    """
    from modules.users.model import UserTable

    created = await in_session(
        lambda: user_service.create_super_admin(form_data=_super_admin_form())
    )

    async with session_scope():
        detail = await UserTable.find_detail_by_id(created.id)
        assert detail is not None
        assert detail["username"] == "rescue"
        assert detail["role_ids"] == [bootstrap_db]

        row = await UserTable.find_by_id(created.id)
        assert row is not None
        assert row.auth_version == 1

        assert await SystemStateTable.exists(SUPER_ADMIN_BOOTSTRAP_KEY) is True
        assert await user_service.bootstrap_available(REGISTER_KEY) is False


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cli_create_super_admin_allows_a_second_one(bootstrap_db):
    """與 signup 的關鍵差別：CLI 沒有「只能一次」的限制。

    latch 已經存在時不重複寫入，`value` 仍指向第一個超級管理者。
    """
    from modules.users.model import UserTable

    await in_session(
        lambda: user_service.signup_user(
            form_data=_signup_form("first"),
            expected_key=REGISTER_KEY,
        )
    )

    await in_session(
        lambda: user_service.create_super_admin(form_data=_super_admin_form("second"))
    )

    assert await count(UserTable) == 2
    assert await count(SystemStateTable) == 1

    async with session_scope() as session:
        latch = (
            await session.scalars(
                select(SystemStateTable).where(SystemStateTable.key == SUPER_ADMIN_BOOTSTRAP_KEY)
            )
        ).first()
        assert latch is not None
        assert latch.value == {"username": "first"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cli_create_super_admin_rejects_duplicate_username(bootstrap_db):
    from modules.users.model import UserTable

    await in_session(lambda: user_service.create_super_admin(form_data=_super_admin_form()))

    with pytest.raises(LangException) as exc_info:
        await in_session(lambda: user_service.create_super_admin(form_data=_super_admin_form()))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == UserError.USERNAME_EXISTS.value.zh
    assert await count(UserTable) == 1


def test_create_super_admin_is_not_exposed_over_http():
    """這條路徑繞過 `validate_role_ids`，授權模型是「呼叫者握有伺服器 shell」。

    一旦有人把它接上 router，授權模型就悄悄換成了「某個 permission」——
    那是完全不同的一件事，而且從 diff 上看起來只是「多了一個端點」。
    """
    from app.server import app

    for route in app.routes:
        endpoint = getattr(route, "endpoint", None)
        assert endpoint is not user_service.create_super_admin
        assert "create_super_admin" not in getattr(endpoint, "__name__", "")


@pytest_asyncio.fixture
async def client():
    """本檔案自己的 client：不套用 tests/modules/conftest.py 那份的使用者 fixture。"""
    from app.server import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client
