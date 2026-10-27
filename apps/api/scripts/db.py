"""DB 管理 CLI — reset / migrate / create-superuser / revoke-sessions

在 api 容器裡執行 (`docker exec -it <專案名>-api python scripts/db.py <子指令>`):
  python scripts/db.py reset                # 清空所有資料表 (dev only)
  python scripts/db.py migrate              # 升到最新結構 + 補齊初始資料 (migrate service 用它)
  python scripts/db.py create-superuser     # 互動式建立超級管理者
  python scripts/db.py revoke-sessions      # 讓所有使用者都要重新登入
"""

import asyncio
import getpass
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _async_url() -> str:
    return os.environ["POSTGRES_URL"]


def _engine():
    from shared.db.session import configure_session_factory, create_engine

    engine = create_engine(_async_url())
    configure_session_factory(engine)
    return engine


# ── seed ──────────────────────────────────────────────────────────────────────


async def _seed():
    """補齊各資料表的初始資料。只由 `cmd_migrate` 呼叫, 不單獨開放: 沒有結構就沒有地方寫。"""
    from app.registry import TABLE_MODELS
    from shared.db.session import session_scope
    from shared.db.table import seed_tables

    engine = _engine()
    try:
        async with session_scope() as session:
            await seed_tables(TABLE_MODELS, session)
    finally:
        await engine.dispose()


# ── reset ─────────────────────────────────────────────────────────────────────


async def cmd_reset():
    if os.environ.get("MODE") != "development":
        print("錯誤：reset 只能在 MODE=development 執行")
        sys.exit(1)

    from sqlalchemy import text

    engine = _engine()
    try:
        async with engine.begin() as connection:
            # 整個 schema 砍掉重建, 而不是逐張 DROP TABLE: 外鍵讓刪除有順序,
            # 逐張刪要自己算拓撲排序, 而那份順序會隨著新增關聯默默失效。
            # `alembic_version` 也在 public 底下, 所以一起消失 —— 那正是我們要的:
            # 之後的 migrate 會把整條 revision 鏈從頭跑一次。
            # **跑完之後一張表都沒有**, 呼叫端要接著跑 migrate (`make db reset` 有做)。
            await connection.execute(text("DROP SCHEMA public CASCADE"))
            await connection.execute(text("CREATE SCHEMA public"))
        print("資料庫已清空。")
    finally:
        await engine.dispose()


# ── migrate ──────────────────────────────────────────────────────────────────


ALEMBIC_INI = Path(__file__).parents[1] / "alembic.ini"


def _alembic_config():
    """指向 apps/api/alembic.ini 的 Config。

    路徑寫死成絕對路徑, 不依賴呼叫時的 CWD: 這支 CLI 在容器裡由 compose 以
    `python scripts/db.py migrate` 執行, 而 alembic 的 `script_location` 是相對
    ini 檔算的 —— 從別的目錄呼叫時, 相對路徑會指到不存在的地方。
    """
    from alembic.config import Config

    return Config(str(ALEMBIC_INI))


def cmd_migrate():
    """把資料庫升到最新的 revision (`alembic upgrade head`), 再補齊初始資料 (seed)。

    **這是資料表與初始資料唯一的寫入路徑。** api 開機時不寫任何東西, 所以一個全新的資料庫
    在這支跑完之前是空的 —— 第一支 migration 就是建表的那一支。

    seed 放在這裡而不是 api 開機時: `make start` 先單獨跑 migrate 服務、失敗就不切換,
    seed 失敗也該被同一道保護擋下。兩段不在同一個交易裡 (alembic 自己管交易), seed 失敗時
    結構已經升上去了 —— 跟 migration 本身一樣, 往前修好再跑一次即可, upsert 可以重複執行。
    """
    from alembic import command

    command.upgrade(_alembic_config(), "head")
    asyncio.run(_seed())


# ── create-superuser ─────────────────────────────────────────────────────────


def _prompt_required(label: str) -> str:
    while True:
        value = input(label).strip()
        if value:
            return value
        print("  不可為空")


def _prompt_password() -> str:
    """用 getpass 而不是 input: 密碼不該回顯在終端機上。

    也**不**從 sys.argv 取 —— 那會留在 shell history 與同機其他使用者的 `ps` 輸出裡。
    """
    while True:
        password = getpass.getpass("密碼（至少 8 字元）：")
        if not password:
            print("  不可為空")
            continue
        if password != getpass.getpass("再次輸入密碼："):
            print("  兩次輸入不一致")
            continue
        return password


async def cmd_create_superuser():
    """建立一個擁有全部權限的超級管理者。

    這是唯一的建立路徑 (網頁上沒有入口, 見 `modules.users.superuser`), 用途有三個:
    部署完成後建立第一個超管、需要第二個超管的場景, 以及唯一超管失聯時的救援。
    """
    from pydantic import ValidationError

    from modules.users.public import create_super_admin
    from modules.users.schema import SuperAdminCreate
    from shared.db.session import session_scope
    from shared.http.errors import LangException

    print("建立超級管理者（此帳號擁有全部權限）")
    nickname = _prompt_required("暱稱：")
    username = _prompt_required("帳號：")
    password = _prompt_password()

    try:
        form_data = SuperAdminCreate(username=username, nickname=nickname, password=password)
    except ValidationError as exc:
        # 只印訊息, 不吐 traceback —— 這是使用者輸入錯誤, 不是程式壞掉。
        for error in exc.errors():
            print(f"錯誤：{'.'.join(str(loc) for loc in error['loc'])} {error['msg']}")
        sys.exit(1)

    engine = _engine()
    try:
        async with session_scope():
            user = await create_super_admin(form_data=form_data)
    except LangException as exc:
        print(f"錯誤：{exc.detail}")
        sys.exit(1)
    finally:
        await engine.dispose()

    print(f"已建立超級管理者：{username}（id: {user.id}）")


async def cmd_revoke_sessions():
    """讓所有使用者既有的 session 立刻失效。確認由 `make db revoke-sessions` 負責。"""
    from modules.users.public import revoke_all_sessions
    from shared.db.session import session_scope

    engine = _engine()
    try:
        async with session_scope():
            result = await revoke_all_sessions()
    finally:
        await engine.dispose()

    print(f"已讓 {result.affected} 位使用者的登入失效，所有人都要重新登入")


# ── 入口 ──────────────────────────────────────────────────────────────────────

COMMANDS = {
    "reset": lambda: asyncio.run(cmd_reset()),
    "migrate": cmd_migrate,
    "create-superuser": lambda: asyncio.run(cmd_create_superuser()),
    "revoke-sessions": lambda: asyncio.run(cmd_revoke_sessions()),
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in COMMANDS:
        print(f"未知命令：{cmd!r}\n可用：{', '.join(COMMANDS)}")
        sys.exit(1)
    COMMANDS[cmd]()
