"""Add action_executions table for durable workflow state.

Revision ID: 003_add_action_executions
Revises: 002_add_compliance_cases
Create Date: 2026-04-11 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003_add_action_executions"
down_revision: Union[str, None] = "002_add_compliance_cases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "action_executions",
        sa.Column("execution_id", sa.String(length=36), nullable=False),
        sa.Column("action_id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column(
            "dry_run",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("input_payload", sa.JSON(), nullable=False),
        sa.Column("requested_by", sa.String(length=36), nullable=False),
        sa.Column(
            "requested_at",
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
        sa.Column(
            "approval_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("approver_role", sa.String(length=100), nullable=True),
        sa.Column("approval_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.String(length=36), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_comment", sa.Text(), nullable=True),
        sa.Column(
            "escalated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("escalation_target", sa.String(length=100), nullable=True),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("audit_events", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("execution_id"),
    )

    op.create_index(
        "ix_action_executions_tenant_requested_at",
        "action_executions",
        ["tenant_id", "requested_at"],
        unique=False,
    )
    op.create_index(
        "ix_action_executions_tenant_status",
        "action_executions",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_action_executions_tenant_action",
        "action_executions",
        ["tenant_id", "action_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_action_executions_tenant_action", table_name="action_executions")
    op.drop_index("ix_action_executions_tenant_status", table_name="action_executions")
    op.drop_index(
        "ix_action_executions_tenant_requested_at",
        table_name="action_executions",
    )
    op.drop_table("action_executions")
