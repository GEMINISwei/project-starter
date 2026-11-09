"""外鍵違反的判斷 (`shared/db/table.py`)。

轉成哪一種訊息依**觸發錯誤的 SQL 種類**: PostgreSQL 對「刪除時仍被參照」與「寫入時參照不存在」
給的 SQLSTATE、資料表與約束名稱完全相同, 只有 detail 文字不同, 而那段文字會隨語系變。
"""

from sqlalchemy.exc import IntegrityError

from shared.db.table import ForeignKeyError, foreign_key_error, is_foreign_key_violation


class _DriverError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


def _integrity_error(sqlstate: str, statement: str = "DELETE FROM parents") -> IntegrityError:
    return IntegrityError(statement, {}, _DriverError(sqlstate))


def test_is_foreign_key_violation_matches_only_sqlstate_23503():
    assert is_foreign_key_violation(_integrity_error("23503")) is True
    assert is_foreign_key_violation(_integrity_error("23505")) is False
    assert is_foreign_key_violation(_integrity_error("23502")) is False
    assert is_foreign_key_violation(ValueError("23503")) is False


def test_foreign_key_error_depends_on_statement_kind():
    """DELETE 是被參照的一方; INSERT 與 UPDATE 是參照的一方 (主鍵是 UUID, 不會被改)。"""
    assert foreign_key_error(_integrity_error("23503", "DELETE FROM parents WHERE id = $1")) is (
        ForeignKeyError.STILL_REFERENCED
    )
    assert foreign_key_error(_integrity_error("23503", "  delete from parents")) is (
        ForeignKeyError.STILL_REFERENCED
    )
    assert foreign_key_error(_integrity_error("23503", "INSERT INTO children VALUES ($1)")) is (
        ForeignKeyError.REFERENCE_NOT_FOUND
    )
    assert foreign_key_error(_integrity_error("23503", "UPDATE children SET parent_id = $1")) is (
        ForeignKeyError.REFERENCE_NOT_FOUND
    )
