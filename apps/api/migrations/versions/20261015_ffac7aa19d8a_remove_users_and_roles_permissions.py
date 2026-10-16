"""remove users and roles permissions

Revision ID: ffac7aa19d8a
Revises: 959dc24d48e4
Create Date: 2026-10-15 21:41:51.968891

後台 (使用者、角色) 改成只開放給超級管理者, `users:*` 與 `roles:*` 這些權限從 `Permission`
enum 移除。角色的 `permissions` 欄位是不受約束的 `text[]`, 舊的字串會留在資料庫裡; 讀出來
經過 `list[Permission]` 驗證時就是 500, 所以這裡把它們從每個角色上拿掉。

只拿掉這兩組前綴, 不動其他值 (例如超級管理者角色的 `*`)。不可逆: 被拿掉的權限本來就不再
有任何作用, downgrade 不嘗試還原。
"""

from collections.abc import Sequence

from alembic import op

revision: str = 'ffac7aa19d8a'
down_revision: str | Sequence[str] | None = '959dc24d48e4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE roles
        SET permissions = ARRAY(
            SELECT permission FROM unnest(permissions) AS permission
            WHERE permission NOT LIKE 'users:%' AND permission NOT LIKE 'roles:%'
        )
        WHERE EXISTS (
            SELECT 1 FROM unnest(permissions) AS permission
            WHERE permission LIKE 'users:%' OR permission LIKE 'roles:%'
        )
        """
    )


def downgrade() -> None:
    pass
