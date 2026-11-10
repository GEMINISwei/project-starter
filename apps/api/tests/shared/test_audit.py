"""AUDIT 紀錄的共用格式 (`shared/audit.py`)。

安全事件事後調查時要 `grep AUDIT` 就挑得出來, 而且每一筆都要對得上是哪個請求、誰、從哪裡。
"""

import contextvars
import logging

from shared.audit import audit
from shared.http.context import current_client_ip, current_request_id, current_user_id


def _in_request(request_id: str, user_id: str, ip: str) -> None:
    current_request_id.set(request_id)
    current_user_id.set(user_id)
    current_client_ip.set(ip)
    audit("user_disabled", user_id="7")


def test_audit_line_has_request_id_actor_and_ip(audit_records: list[logging.LogRecord]):
    contextvars.copy_context().run(_in_request, "a1b2c3d4", "42", "203.0.113.7")

    assert [record.getMessage() for record in audit_records] == [
        "AUDIT [a1b2c3d4] user_disabled actor=42 ip=203.0.113.7 user_id=7"
    ]


def test_audit_outside_request_uses_dashes(audit_records: list[logging.LogRecord]):
    """CLI (例如建立超管) 沒有請求、也沒有登入者。"""
    contextvars.Context().run(audit, "superuser_created", user_id="1")

    assert [record.getMessage() for record in audit_records] == [
        "AUDIT [-] superuser_created actor=- ip=- user_id=1"
    ]


def test_audit_value_cannot_forge_a_new_line(audit_records: list[logging.LogRecord]):
    """路徑之類的值來自外部: 帶換行的話, 一筆紀錄可以偽造出另一行假的紀錄。"""
    contextvars.Context().run(audit, "permission_denied", path="/a b\nINFO: AUDIT fake")

    message = audit_records[0].getMessage()
    assert "\n" not in message
    assert message.endswith('path="/a b\\nINFO: AUDIT fake"')
