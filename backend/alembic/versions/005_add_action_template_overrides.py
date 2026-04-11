"""Add action_template_overrides table for tenant workflow template configuration.

Revision ID: 005_add_action_template_overrides
Revises: 004_add_compliance_attestations
Create Date: 2026-04-11 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "005_add_action_template_overrides"
down_revision: Union[str, None] = "004_add_compliance_attestations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "action_template_overrides",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("action_id", sa.String(length=64), nullable=False),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column("trigger_override", sa.String(length=120), nullable=True),
        sa.Column("approval_required_override", sa.Boolean(), nullable=True),
        sa.Column("approver_role_override", sa.String(length=100), nullable=True),
        sa.Column("sla_hours_override", sa.Integer(), nullable=True),
        sa.Column("execution_steps_override", sa.JSON(), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=False),
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
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_action_template_overrides_tenant_action",
        "action_template_overrides",
        ["tenant_id", "action_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_action_template_overrides_tenant_action",
        table_name="action_template_overrides",
    )
    op.drop_table("action_template_overrides")
