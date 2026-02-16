"""Add subscriptions and usage_daily

Revision ID: 004
Revises: 003
Create Date: 2026-02-06

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(connection, name: str) -> bool:
    result = connection.execute(text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=:name"
    ), {"name": name})
    return result.fetchone() is not None


def upgrade() -> None:
    conn = op.get_bind()
    if not _table_exists(conn, "subscriptions"):
        op.create_table(
            "subscriptions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("tier", sa.String(20), nullable=True),
            sa.Column("stars_paid_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_subscriptions_user_id"), "subscriptions", ["user_id"], unique=True)

    if not _table_exists(conn, "usage_daily"):
        op.create_table(
            "usage_daily",
            sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("date", sa.String(10), nullable=False),
            sa.Column("count", sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_usage_daily_user_id"), "usage_daily", ["user_id"], unique=False)
        op.create_index(op.f("ix_usage_daily_date"), "usage_daily", ["date"], unique=False)


def downgrade() -> None:
    op.drop_table("usage_daily")
    op.drop_table("subscriptions")
