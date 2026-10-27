"""service 回傳建構好的 pydantic model, 不回傳 dict。

回傳型別註記由 mypy (`disallow_untyped_defs`) 強制, 但 `-> dict` 一樣過得了 mypy。
router 收到 dict 時 FastAPI 照樣依 `response_model` 序列化, 錯的欄位要到執行期才看得到,
而且 service 之間互相呼叫時拿到的是沒有形狀的 dict。

service 檔用排除法認: 依授權模型拆出來的新檔 (例: users 的 `account.py`) 不必另外登記。
"""

import importlib
import inspect
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType, NoneType
from typing import Any, get_type_hints

from pydantic import BaseModel

MODULES = Path(__file__).parents[1] / "modules"

# 這些檔案不是 service: 宣告、資料表、HTTP 轉接或對外介面。
NOT_SERVICE_FILES = {
    "__init__",
    "errors",
    "manifest",
    "model",
    "permissions",
    "public",
    "router",
    "schema",
}


def service_modules() -> Iterator[ModuleType]:
    for path in sorted(MODULES.glob("*/*.py")):
        if path.stem not in NOT_SERVICE_FILES:
            yield importlib.import_module(f"modules.{path.parent.name}.{path.stem}")


def public_functions(module: ModuleType) -> Iterator[Callable[..., Any]]:
    for name, func in inspect.getmembers(module, inspect.isfunction):
        if func.__module__ == module.__name__ and not name.startswith("_"):
            yield func


def returns_model_or_none(func: Callable[..., Any]) -> bool:
    returned = get_type_hints(func).get("return")
    if returned is NoneType:
        return True
    return isinstance(returned, type) and issubclass(returned, BaseModel)


def test_service_modules_are_found() -> None:
    names = {module.__name__ for module in service_modules()}
    assert "modules.roles.service" in names


def test_service_functions_return_pydantic_models() -> None:
    offenders = [
        f"{func.__module__}.{func.__name__}"
        for module in service_modules()
        for func in public_functions(module)
        if not returns_model_or_none(func)
    ]
    assert offenders == [], "service 要回傳建構好的 pydantic model (或 None), 不回傳 dict"


def test_return_check_rejects_dict() -> None:
    async def get_item() -> dict[str, str]:
        return {}

    assert not returns_model_or_none(get_item)


def test_return_check_accepts_model_and_none() -> None:
    class Item(BaseModel):
        id: str

    async def get_item() -> Item:
        return Item(id="1")

    async def validate_item() -> None:
        return None

    assert returns_model_or_none(get_item)
    assert returns_model_or_none(validate_item)
