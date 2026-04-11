"""Add compliance_attestations table for signed compliance proofs.

Revision ID: 004_add_compliance_attestations
Revises: 003_add_action_executions
Create Date: 2026-04-11 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "004_add_compliance_attestations"
down_revision: Union[str, None] = "003_add_action_executions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "compliance_attestations",
        sa.Column("attestation_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("framework", sa.String(length=40), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_by", sa.String(length=36), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_digest", sa.String(length=64), nullable=False),
        sa.Column("signature_algorithm", sa.String(length=32), nullable=False),
        sa.Column("signature", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("attestation_id"),
    )

    op.create_index(
        "ix_compliance_attestations_tenant_framework_created_at",
        "compliance_attestations",
        ["tenant_id", "framework", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_compliance_attestations_tenant_period",
        "compliance_attestations",
        ["tenant_id", "period_start", "period_end"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_compliance_attestations_tenant_period",
        table_name="compliance_attestations",
    )
    op.drop_index(
        "ix_compliance_attestations_tenant_framework_created_at",
        table_name="compliance_attestations",
    )
    op.drop_table("compliance_attestations")
