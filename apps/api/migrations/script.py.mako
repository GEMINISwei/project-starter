"""${message}

Revision ID: ${up_revision}
Revises:${" " + down_revision if down_revision else ""}
Create Date: ${create_date}

產生之後**自己讀一遍再 commit, 並把「為什麼」補進這段 docstring**。autogenerate 是 diff
工具, 不是設計工具 —— 底下的 SQL 已經寫了「做了什麼」, 寫不出來的是「為什麼這個欄位要有
預設值」「為什麼這次要順便回填」。它固定會漏掉三件事:

- **資料。** 往有資料的表加一個 NOT NULL 欄位, 它只寫 ADD COLUMN, 不會回填, 跑起來直接失敗。
- **改名。** 欄位或表改名會被看成「drop 一個、add 一個」, 照著跑資料就沒了。
- **不能在交易裡跑的東西** (`CREATE INDEX CONCURRENTLY`)。整批 migration 包在一個交易裡,
  見 migrations/env.py。

確認完把這三行說明刪掉, 換成這支 migration 自己的理由。
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
## mako 的控制行本身不產生換行, 所以 imports 是空的時候不會多留一個空行。
## 寫成 `${imports if imports else ""}` 的話空的那個 case 會多一行, 而 ruff 的 I001 會紅。
% if imports:
${imports}
% endif

revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
