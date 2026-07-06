"""Quotas, audit log, duration estimate.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("daily_minutes_limit", sa.Float(), nullable=True))
    op.add_column("users", sa.Column("monthly_minutes_limit", sa.Float(), nullable=True))
    op.add_column("jobs", sa.Column("estimated_duration", sa.Float(), nullable=True))

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(32), nullable=True),
        sa.Column("username", sa.String(150), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("ip", sa.String(64), nullable=True),
    )
    op.create_index("ix_audit_created", "audit_log", ["created_at"])
    op.create_index("ix_audit_log_user_id", "audit_log", ["user_id"])
    op.create_index("ix_audit_log_action", "audit_log", ["action"])


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_column("jobs", "estimated_duration")
    op.drop_column("users", "monthly_minutes_limit")
    op.drop_column("users", "daily_minutes_limit")
