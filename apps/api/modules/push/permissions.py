from app.permissions import Permission
from shared.http.errors import LangText
from shared.module import PermissionSpec

PERMISSIONS = (
    PermissionSpec(
        Permission.PUSH_SEND,
        LangText(zh="推播：廣播通知", en="Push: Broadcast"),
        assignable=False,
    ),
)
