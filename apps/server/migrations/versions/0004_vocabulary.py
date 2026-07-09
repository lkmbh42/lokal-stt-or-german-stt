"""Per-user custom vocabulary.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vocabulary_entries",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(32),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("term", sa.String(200), nullable=False),
        sa.Column("variants", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_vocabulary_entries_user_id", "vocabulary_entries", ["user_id"])
    op.create_index("ix_vocab_user", "vocabulary_entries", ["user_id"])


def downgrade() -> None:
    op.drop_table("vocabulary_entries")
