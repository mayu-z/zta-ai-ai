"""Add IntentDetectionKeyword table for database-driven intent keyword detection.

Revision ID: 001_add_intent_detection_keywords
Revises: 
Create Date: 2025-01-01 00:00:00.000000

This migration introduces the `intent_detection_keywords` table which enables
database-driven configuration of keywords used to detect specific intents
(e.g., grade markers for student_grades intent). This removes the need for
hardcoded keyword lists in Python code.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001_add_intent_detection_keywords"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create intent_detection_keywords table."""
    op.create_table(
        "intent_detection_keywords",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("tenant_id", sa.String(36), nullable=False),
        sa.Column("intent_name", sa.String(120), nullable=False),
        sa.Column("keyword_type", sa.String(50), nullable=False),
        sa.Column("keyword", sa.String(255), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create indexes for efficient querying
    op.create_index(
        "ix_intent_detection_keywords_tenant_intent_type",
        "intent_detection_keywords",
        ["tenant_id", "intent_name", "keyword_type"],
        unique=False,
    )
    op.create_index(
        "ix_intent_detection_keywords_tenant_keyword",
        "intent_detection_keywords",
        ["tenant_id", "intent_name", "keyword", "keyword_type"],
        unique=True,
    )


def downgrade() -> None:
    """Drop intent_detection_keywords table."""
    op.drop_index(
        "ix_intent_detection_keywords_tenant_keyword",
        table_name="intent_detection_keywords",
    )
    op.drop_index(
        "ix_intent_detection_keywords_tenant_intent_type",
        table_name="intent_detection_keywords",
    )
    op.drop_table("intent_detection_keywords")
