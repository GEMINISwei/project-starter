"""權限 metadata 由啟用中的 manifest 各自擁有，並只彙整一次。"""

import pytest

from app.permissions import (
    Permission,
    build_permission_catalog,
    validate_permission_coverage,
)
from app.registry import ENABLED_MODULES
from shared.http.errors import LangText, Language, current_language
from shared.module import PermissionSpec


@pytest.fixture
def catalog():
    """完整啟用清單組出來的目錄，等同 `create_app()` 掛到 `app.state` 的那一份。"""
    return build_permission_catalog(
        spec for module in ENABLED_MODULES for spec in module.permissions
    )


def test_every_permission_has_exactly_one_feature_spec(catalog):
    assert set(catalog.specs) == set(Permission) - {Permission.ALL}


def test_assignable_list_matches_feature_metadata(catalog):
    values = {item["value"] for item in catalog.assignable_permissions()}
    expected = {permission.value for permission, spec in catalog.specs.items() if spec.assignable}
    assert values == expected


def test_assignable_labels_are_human_readable(catalog):
    raw = [
        item["value"] for item in catalog.assignable_permissions() if item["label"] == item["value"]
    ]
    assert raw == []


def test_assignable_labels_follow_current_language(catalog):
    """標籤是 `LangText`，要跟著這次請求的語系走。

    這份清單是角色編輯頁的勾選項目，前端直接顯示後端給的 label（`PermissionChecklist`
    只負責排版）。所以語系取錯的話，英文使用者會在英文介面裡看到一整排中文權限名稱，
    而前端沒有任何機制會發現 —— 它拿到什麼就畫什麼。
    """
    zh_labels = {item["value"]: item["label"] for item in catalog.assignable_permissions()}

    token = current_language.set(Language.EN)
    try:
        en_labels = {item["value"]: item["label"] for item in catalog.assignable_permissions()}
    finally:
        current_language.reset(token)

    assert zh_labels.keys() == en_labels.keys()
    # 至少有一個真的不一樣 —— 全部相同代表語系根本沒生效（或所有 LangText 都填了同樣的字）。
    assert any(zh_labels[value] != en_labels[value] for value in zh_labels)


def test_dependency_targets_are_real_permissions(catalog):
    valid = set(Permission)
    for spec in catalog.specs.values():
        assert set(spec.dependencies) <= valid


def test_resolver_expands_declared_dependencies(catalog):
    """resolver 跟著目錄一起建出來，相依展開才不會與 metadata 脫節。"""
    expanded = catalog.resolver.expand({Permission.USER_MANAGE})
    assert Permission.USER_UPDATE_ANY in expanded


def test_permission_catalog_rejects_missing_metadata():
    with pytest.raises(RuntimeError, match="permission metadata mismatch"):
        validate_permission_coverage(())


def test_permission_catalog_rejects_duplicate_metadata():
    duplicate = PermissionSpec(Permission.USER_READ, LangText(zh="使用者", en="Users"))
    with pytest.raises(RuntimeError, match="duplicate permission spec"):
        build_permission_catalog((duplicate, duplicate))
