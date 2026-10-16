"""這個專案的註冊表 (`app/registry.py`) 與註冊在上面的資料表要遵守的慣例。

與 `tests/shared/` 不同, 這裡針對的是**實際啟用的** modules, 所以不隨 shared 一起移植。
"""

import inspect
from typing import get_args, get_type_hints, is_typeddict

import pytest
from sqlalchemy import DateTime

from app.registry import ENABLED_MODULES, TABLE_MODELS
from app.server import create_app
from shared.time import utc_now


def _public_classmethods(cls):
    seen: set[str] = set()
    for klass in cls.__mro__:
        for name, member in vars(klass).items():
            if name.startswith("_") or name in seen:
                continue
            if isinstance(member, classmethod):
                seen.add(name)
                yield f"{klass.__name__}.{name}", member.__func__


def test_base_table_declares_the_shared_columns():
    """`id` / `created_at` / `updated_at` 是全專案共用的欄位契約。

    分頁的 tie-breaker (`id`) 與預設排序 (`created_at`) 都建立在它們身上;
    在子類別把其中一個改名或拿掉, 症狀是分頁在執行期才炸。
    """
    for model in TABLE_MODELS:
        columns = set(model.__table__.columns.keys())
        assert {"id", "created_at", "updated_at"} <= columns, model.__name__


def _returns_dict_shape(func) -> bool:
    """回傳型別是不是「加工過的 dict」而不是 ORM 實例。

    TypedDict 也算 —— 它在執行期就是 dict, 只是額外標明了有哪些鍵
    (例如 `find_detail_by_username` 回傳 `CurrentUser`)。這個測試守的是
    `find_detail_*` 與 `find_*` 的分工, 不是「註記必須逐字寫成 dict」。
    """
    annotation = str(inspect.signature(func).return_annotation)
    if "dict" in annotation:
        return True
    return any(is_typeddict(candidate) for candidate in _annotated_types(func))


def _annotated_types(func):
    """把回傳註記解析成實際型別, `X | None` 這種聯集會拆開逐一回傳。"""
    try:
        hints = get_type_hints(func)
    except Exception:
        return []
    returned = hints.get("return")
    return [arg for arg in get_args(returned)] or [returned]


def test_find_detail_methods_return_dict():
    for model in TABLE_MODELS:
        for qualname, func in _public_classmethods(model):
            if ".find_detail" in qualname:
                assert _returns_dict_shape(func), qualname


def test_find_by_methods_do_not_return_dict():
    for model in TABLE_MODELS:
        for qualname, func in _public_classmethods(model):
            if ".find_by" in qualname:
                assert not _returns_dict_shape(func), qualname


def _removable_modules():
    """有資料表或權限可供驗證的 module, 逐一當成停用對象。"""
    return [module for module in ENABLED_MODULES if module.tables or module.permissions]


@pytest.mark.parametrize("target", _removable_modules(), ids=lambda module: module.name)
def test_create_app_can_disable_any_module_without_touching_the_others(target):
    remaining = tuple(module for module in ENABLED_MODULES if module.name != target.name)
    application = create_app(remaining)

    assert target.name not in {module.name for module in application.state.modules}
    installed = {model.__name__ for model in application.state.table_models}
    assert installed.isdisjoint({model.__name__ for model in target.tables})
    # 其餘模組必須原封不動 —— 這才是「不必修改其他 module」那句話的實質內容。
    assert [module.name for module in application.state.modules] == [
        module.name for module in remaining
    ]


def test_enabled_modules_provide_exactly_one_current_user_resolver():
    """身分來源只能有一個, 而且必須真的有人提供。

    這條守的是「組裝層不認識具名 module」那個設計: `app/server.py` 不再 import
    `modules.users`, 改由 manifest 提供。少了這個測試, 把 users 的
    `current_user_resolver=` 刪掉不會有任何靜態錯誤, 服務照常啟動,
    直到第一個帶 token 的請求進來才炸。
    """
    providers = [
        module.name for module in ENABLED_MODULES if module.current_user_resolver is not None
    ]

    # 只斷言「剛好一個」, 不寫死是哪個模組: 身分來源換成別的模組是合法的改法。
    assert len(providers) == 1, providers


@pytest.mark.parametrize(
    "target",
    [module for module in _removable_modules() if module.permissions],
    ids=lambda module: module.name,
)
def test_disabling_a_module_also_removes_its_permissions_from_the_catalog(target):
    """停用 module 之後, 它的權限不該還出現在可指派清單裡。

    權限目錄是由 `create_app()` 依實際啟用的 modules 建的。若改回在 import 當下用全域
    清單建, 這裡就會抓到 —— 那時 `GET /permissions/` 會繼續提供一個已經沒有路由的權限。
    """
    remaining = tuple(module for module in ENABLED_MODULES if module.name != target.name)
    application = create_app(remaining)

    catalog = application.state.permission_catalog
    values = {item["value"] for item in catalog.assignable_permissions()}
    removed = {str(spec.value) for spec in target.permissions}
    kept = {
        str(spec.value)
        for module in remaining
        for spec in module.permissions
        if spec.assignable
    }
    assert values.isdisjoint(removed)
    assert kept <= values


def test_two_apps_do_not_share_a_permission_catalog():
    """同一個行程裡的兩個 app 各有各的權限目錄。

    目錄掛在 `app.state` 而不是行程層級的全域。若是後者, 第二次 `create_app()` 會
    **靜靜換掉**第一個 app 的目錄, `GET /permissions/` 從此回答錯誤的內容 ——
    沒有例外、沒有警告, 而症狀取決於呼叫順序。
    """
    # 目前沒有任何 module 提供權限 (後台只開放給超級管理者), 那時退而求其次停用任一個:
    # 權限集合的斷言會是空集合而恆真, 但 resolver 各自一份那條仍然有效。
    candidates = _removable_modules()
    target = next((module for module in candidates if module.permissions), candidates[0])
    remaining = tuple(module for module in ENABLED_MODULES if module.name != target.name)

    full_app = create_app(ENABLED_MODULES)
    partial_app = create_app(remaining)

    full_values = {
        item["value"] for item in full_app.state.permission_catalog.assignable_permissions()
    }
    partial_values = {
        item["value"] for item in partial_app.state.permission_catalog.assignable_permissions()
    }
    assignable = {str(spec.value) for spec in target.permissions if spec.assignable}

    # 第一個 app 不受第二個影響: 被停用的那些權限仍在它自己的目錄裡。
    assert assignable <= full_values
    assert partial_values.isdisjoint(assignable)
    # resolver 也是各自一份, 否則相依展開會跟著最後一次組裝走。
    assert full_app.state.permission_resolver is not partial_app.state.permission_resolver


def test_created_at_defaults_to_utc_now():
    """避免有人在某個 model 把預設值換回 `datetime.now` (本地時間) 或資料庫的 `now()` (帶時區)。"""
    for model in TABLE_MODELS:
        default = model.__table__.columns["created_at"].default
        assert default is not None, model.__name__
        # SQLAlchemy 會把零參數的 callable 包一層 (讓它收得到 execution context),
        # 原本那個掛在 `__wrapped__` 上 —— 比對包裝後的物件永遠不會相等。
        assert getattr(default.arg, "__wrapped__", default.arg) is utc_now, model.__name__


def test_timestamps_are_stored_without_timezone():
    """欄位型別必須是 `TIMESTAMP WITHOUT TIME ZONE` (理由見 tests/shared/test_time.py)。"""
    for model in TABLE_MODELS:
        for column in ("created_at", "updated_at"):
            column_type = model.__table__.columns[column].type
            assert isinstance(column_type, DateTime), model.__name__
            assert column_type.timezone is False, model.__name__
