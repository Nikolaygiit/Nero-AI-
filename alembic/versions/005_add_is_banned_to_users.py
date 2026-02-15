"""Add is_banned to users

Revision ID: 005
Revises: 004
Create Date: 2026-02-07

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(connection, table: str, column: str) -> bool:
    # pragma_table_info не поддерживает bound params в старых SQLite
    result = connection.execute(text(f"SELECT 1 FROM pragma_table_info('{table}') WHERE name='{column}'"))
    return result.fetchone() is not None


def upgrade() -> None:
    conn = op.get_bind()
    if not _column_exists(conn, "users", "is_banned"):
        op.add_column("users", sa.Column("is_banned", sa.Boolean(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("users", "is_banned")
