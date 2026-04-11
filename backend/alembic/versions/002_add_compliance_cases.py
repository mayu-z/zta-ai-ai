"""Add compliance_cases table for durable compliance workflow state.

Revision ID: 002_add_compliance_cases
Revises: 001_add_intent_detection_keywords
Create Date: 2026-04-11 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002_add_compliance_cases"
down_revision: Union[str, None] = "001_add_intent_detection_keywords"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "compliance_cases",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("case_type", sa.String(length=40), nullable=False),
        sa.Column("subject_identifier", sa.String(length=255), nullable=False),
        sa.Column("action_execution_id", sa.String(length=36), nullable=False),
        sa.Column("requested_by", sa.String(length=36), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("delivery_method", sa.String(length=40), nullable=True),
        sa.Column("legal_basis", sa.String(length=120), nullable=True),
        sa.Column(
            "legal_hold_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("legal_hold_reason", sa.Text(), nullable=True),
        sa.Column("last_action_status", sa.String(length=40), nullable=True),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("case_events", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_compliance_cases_tenant_requested_at",
        "compliance_cases",
        ["tenant_id", "requested_at"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_cases_tenant_case_type_status",
        "compliance_cases",
        ["tenant_id", "case_type", "status"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_cases_tenant_execution",
        "compliance_cases",
        ["tenant_id", "action_execution_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_compliance_cases_tenant_execution", table_name="compliance_cases")
    op.drop_index(
        "ix_compliance_cases_tenant_case_type_status",
        table_name="compliance_cases",
    )
    op.drop_index("ix_compliance_cases_tenant_requested_at", table_name="compliance_cases")
    op.drop_table("compliance_cases")
