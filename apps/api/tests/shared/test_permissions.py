import pytest

from shared.auth.permissions import BasePermission, PermissionResolver


# 繼承 BasePermission 而非裸 StrEnum：`PermissionResolver[PermissionT: BasePermission]`
# 的型別參數有上界，用 StrEnum 會讓每個 resolver 建構都不符合型別約束。
class FakePerm(BasePermission):
    A = "a"
    B = "b"
    C = "c"
    D = "d"


def test_expand_no_dependencies():
    resolver = PermissionResolver(FakePerm)
    result = resolver.expand({FakePerm.A})
    assert result == {FakePerm.A}


def test_expand_empty_set():
    resolver = PermissionResolver(FakePerm)
    result = resolver.expand(set())
    assert result == set()


def test_expand_single_dependency():
    resolver = PermissionResolver(FakePerm, {FakePerm.A: {FakePerm.B}})
    result = resolver.expand({FakePerm.A})
    assert result == {FakePerm.A, FakePerm.B}


def test_expand_chained_dependencies():
    """A → B → C 要展開成 {A, B, C}。"""
    resolver = PermissionResolver(
        FakePerm,
        {FakePerm.A: {FakePerm.B}, FakePerm.B: {FakePerm.C}},
    )
    result = resolver.expand({FakePerm.A})
    assert result == {FakePerm.A, FakePerm.B, FakePerm.C}


def test_expand_does_not_duplicate():
    """展開後的集合不該有重複元素。"""
    resolver = PermissionResolver(
        FakePerm,
        {FakePerm.A: {FakePerm.B, FakePerm.C}, FakePerm.B: {FakePerm.C}},
    )
    result = resolver.expand({FakePerm.A})
    assert result == {FakePerm.A, FakePerm.B, FakePerm.C}
    assert len(result) == 3


def test_expand_multiple_input_permissions():
    resolver = PermissionResolver(FakePerm, {FakePerm.A: {FakePerm.B}})
    result = resolver.expand({FakePerm.A, FakePerm.C})
    assert result == {FakePerm.A, FakePerm.B, FakePerm.C}


def test_validate_invalid_permission_raises():
    class OtherPerm(BasePermission):
        X = "x"

    with pytest.raises(TypeError):
        PermissionResolver(FakePerm, {OtherPerm.X: {FakePerm.A}})  # type: ignore
