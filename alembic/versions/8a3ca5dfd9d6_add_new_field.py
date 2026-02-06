"""add new field

Revision ID: 8a3ca5dfd9d6
Revises: 002
Create Date: 2026-02-06 22:55:37.014529

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a3ca5dfd9d6'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("your_column", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "your_column")
