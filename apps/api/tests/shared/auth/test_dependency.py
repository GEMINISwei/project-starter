"""權限檢查 (`shared/auth/dependency.py`) 留下的 AUDIT 紀錄。

權限設錯時 (使用者說看不到某個頁面), 查 `permission_denied` 就知道他缺哪一個權限。
"""

import logging

import pytest
from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient

from shared.auth.contracts import CurrentUser
from shared.auth.dependency import check_user_permission
from shared.auth.tokens import create_token
from shared.module import ModuleManifest
from tests.audit import events
from tests.shared.minimal_app import MinimalEnv, Permission, create_minimal_app


async def _member_resolver(username: str) -> CurrentUser | None:
    return {
        "id": "member-1",
        "username": username,
        "auth_version": 1,
        "permissions": [],
        "is_disabled": False,
    }


@pytest.mark.asyncio
async def test_permission_denied_is_audited_with_user_and_permission(
    audit_records: list[logging.LogRecord],
):
    router = APIRouter(prefix="/probe")

    @router.get("/admin")
    async def admin_route(
        _: CurrentUser = Depends(check_user_permission(Permission.ALL)),
    ) -> dict[str, bool]:
        return {"ok": True}

    application = create_minimal_app(
        ModuleManifest("probe", routers=(router,), current_user_resolver=_member_resolver)
    )
    token = create_token({"username": "member", "auth_version": 1}, MinimalEnv())
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        client.cookies.set("access_token", token["access_token"])
        response = await client.get(
            "/api/probe/admin",
            headers={"X-Request-ID": "deny123", "X-Real-IP": "203.0.113.7"},
        )

    assert response.status_code == 403
    assert events(audit_records) == [
        (
            "permission_denied",
            {
                "request_id": "deny123",
                "actor": "member-1",
                "ip": "203.0.113.7",
                "required": "*",
                "path": "/api/probe/admin",
            },
        )
    ]
