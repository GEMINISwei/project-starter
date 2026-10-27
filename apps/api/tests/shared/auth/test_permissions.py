import pytest

from shared.auth.permissions import BasePermission, PermissionResolver


# 繼承 BasePermission 而非裸 StrEnum: `PermissionResolver[PermissionT: BasePermission]`
# 的型別參數有上界, 用 StrEnum 會讓每個 resolver 建構都不符合型別約束。
class FakePerm(BasePermission):
    A = "a"
    B = "b"
    C = "c"
    D = "d"


def test_expand_chained_dependencies():
    """A → B → C 要展開成 {A, B, C}。"""
    resolver = PermissionResolver(
        FakePerm,
        {FakePerm.A: {FakePerm.B}, FakePerm.B: {FakePerm.C}},
    )
    result = resolver.expand({FakePerm.A})
    assert result == {FakePerm.A, FakePerm.B, FakePerm.C}


def test_expand_multiple_input_permissions():
    resolver = PermissionResolver(FakePerm, {FakePerm.A: {FakePerm.B}})
    result = resolver.expand({FakePerm.A, FakePerm.C})
    assert result == {FakePerm.A, FakePerm.B, FakePerm.C}


def test_validate_invalid_permission_raises():
    class OtherPerm(BasePermission):
        X = "x"

    with pytest.raises(TypeError):
        PermissionResolver(FakePerm, {OtherPerm.X: {FakePerm.A}})  # type: ignore


class WildPerm(BasePermission):
    ALL = "*"
    A = "a"
    B = "b"
    C = "c"


def test_covers_permissions_reached_through_dependencies():
    """持有 A (A → B) 就涵蓋 B: 比對的是展開後的集合, 不是字面上持有的。"""
    resolver = PermissionResolver(WildPerm, {WildPerm.A: {WildPerm.B}})

    assert resolver.covers(["a"], ["a", "b"]) is True


def test_covers_rejects_permission_outside_the_expanded_set():
    resolver = PermissionResolver(WildPerm, {WildPerm.A: {WildPerm.B}})

    assert resolver.covers(["b"], ["a"]) is False


def test_wildcard_covers_everything():
    resolver = PermissionResolver(WildPerm)

    assert resolver.covers(["*"], ["a", "b", "c", "*"]) is True


def test_only_wildcard_covers_wildcard():
    """`*` 不會從任何一般權限展開出來 —— 一般管理者永遠涵蓋不了超級管理者。"""
    resolver = PermissionResolver(WildPerm, {WildPerm.A: {WildPerm.B, WildPerm.C}})

    assert resolver.covers(["a"], ["*"]) is False


def test_covers_tolerates_unknown_permission_strings():
    """資料庫裡可能留著已停用模組的權限字串, 不能因此丟例外變成 500。"""
    resolver = PermissionResolver(WildPerm)

    assert resolver.covers(["a", "gone:read"], ["a"]) is True
    assert resolver.covers(["a"], ["gone:read"]) is False
