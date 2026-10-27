from collections.abc import Mapping

from httpx import AsyncClient

from app.permissions import Permission
from app.registry import ENABLED_MODULES
from app.server import app
from shared.auth.catalog import build_permission_catalog
from shared.auth.permissions import PermissionResolver
from shared.auth.tokens import create_token


def token_for(username: str) -> str:
    return create_token({"username": username, "auth_version": 1}, app.state.env)["access_token"]


def authenticate(client: AsyncClient, username: str) -> None:
    client.cookies.set("access_token", token_for(username))


def permission_resolver() -> PermissionResolver[Permission]:
    """完整啟用清單的權限展開規則。

    等同 `create_app()` 掛到 `app.state.permission_resolver` 的那一個。

    service 收 resolver 當參數 (不 import 全域), 所以 service 層的測試用這個組一份。
    """
    specs = (spec for module in ENABLED_MODULES for spec in module.permissions)
    return build_permission_catalog(Permission, specs).resolver


def assert_covers(declared: type, actual: Mapping[str, object], label: str) -> None:
    """實際回傳的 dict 要涵蓋 TypedDict 宣告的每一個必填鍵 (給 `test_model.py` 用)。

    只檢查「宣告的都在」, 不檢查「回傳的都有宣告」—— model 本來就會多帶
    `created_at` 這類沒人讀的欄位, 把它們也逼進 TypedDict 只會讓型別變成
    資料表定義的副本, 那正是這些 TypedDict 刻意不做的事。
    """
    missing = set(declared.__required_keys__) - set(actual)  # type: ignore[attr-defined]
    assert not missing, f"{label} 少了這些欄位：{sorted(missing)}（實際有 {sorted(actual)}）"
