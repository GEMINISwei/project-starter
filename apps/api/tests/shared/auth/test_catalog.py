"""權限目錄的通用行為, 用一個只存在於測試裡的 enum 驗證 (不綁任何專案的權限)。"""

import pytest

from shared.auth.catalog import build_permission_catalog, validate_permission_coverage
from shared.auth.permissions import WILDCARD, BasePermission
from shared.http.errors import LangText
from shared.module import PermissionSpec


class _Permission(BasePermission):
    ALL = WILDCARD
    READ = "things:read"
    MANAGE = "things:manage"


THINGS = LangText(zh="物品", en="Things")
READ = PermissionSpec(_Permission.READ, LangText(zh="讀取", en="Read"), THINGS)
MANAGE = PermissionSpec(
    _Permission.MANAGE,
    LangText(zh="管理", en="Manage"),
    THINGS,
    dependencies=frozenset({_Permission.READ}),
)


def test_coverage_accepts_exactly_the_enum_minus_wildcard():
    validate_permission_coverage(_Permission, (READ, MANAGE))


def test_coverage_rejects_missing_metadata():
    with pytest.raises(RuntimeError, match="permission metadata mismatch"):
        validate_permission_coverage(_Permission, (READ,))


def test_catalog_rejects_duplicate_metadata():
    with pytest.raises(RuntimeError, match="duplicate permission spec"):
        build_permission_catalog(_Permission, (READ, READ))


def test_catalog_rejects_metadata_for_the_wildcard():
    """萬用字元不是某個 module 的功能, 誰提供它的 metadata 都是錯的。"""
    wildcard = PermissionSpec(_Permission.ALL, LangText(zh="全部", en="All"), THINGS)
    with pytest.raises(RuntimeError, match="萬用字元"):
        build_permission_catalog(_Permission, (wildcard,))


def test_catalog_may_cover_a_subset():
    """停用某個 module 後組出來的 app 只有部分權限, 這必須是合法的。"""
    catalog = build_permission_catalog(_Permission, (READ,))
    assert catalog.assignable_permissions() == [
        {"value": "things:read", "label": "讀取", "category": "物品"}
    ]


def test_resolver_follows_declared_dependencies():
    catalog = build_permission_catalog(_Permission, (READ, MANAGE))
    assert catalog.resolver.expand({_Permission.MANAGE}) == {_Permission.MANAGE, _Permission.READ}
