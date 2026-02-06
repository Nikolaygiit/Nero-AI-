"""Add user_facts table (RAG Lite)

Revision ID: 003
Revises: 8a3ca5dfd9d6
Create Date: 2026-02-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "003"
down_revision: Union[str, None] = "8a3ca5dfd9d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_facts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("fact_type", sa.String(50), nullable=False),
        sa.Column("fact_value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_user_facts_user_id"), "user_facts", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("user_facts")
