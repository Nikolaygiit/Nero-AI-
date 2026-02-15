"""Add age to users (example migration)

Revision ID: 002
Revises: 001
Create Date: 2025-02-02

Пример: добавление поля "возраст" пользователю без удаления БД.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("age", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "age")
