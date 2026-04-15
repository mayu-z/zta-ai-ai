"""baseline existing schema

Revision ID: 001_baseline_existing_schema
Revises:
Create Date: 2026-04-16 00:00:00
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "001_baseline_existing_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Baseline revision for environments initialized with SQLAlchemy metadata.
    op.execute("SELECT 1")


def downgrade() -> None:
    op.execute("SELECT 1")
