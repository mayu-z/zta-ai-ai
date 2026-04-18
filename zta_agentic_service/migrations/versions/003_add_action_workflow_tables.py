"""add action workflow registry and execution tables

Revision ID: 003_add_action_workflow_tables
Revises: 002_add_agent_templates
Create Date: 2026-04-18 08:25:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "003_add_action_workflow_tables"
down_revision = "002_add_agent_templates"
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    action_type_enum = sa.Enum(
        "privacy",
        "access",
        "governance",
        "operations",
        "reporting",
        "incident",
        name="actiontype",
    )
    rollback_strategy_enum = sa.Enum(
        "soft_delete",
        "compensating_tx",
        "snapshot",
        "none",
        name="actionrollbackstrategy",
    )
    execution_status_enum = sa.Enum(
        "pending",
        "running",
        "awaiting_approval",
        "approved",
        "rejected",
        "completed",
        "failed",
        "rolled_back",
        name="actionexecutionstatus",
    )

    action_type_enum.create(bind, checkfirst=True)
    rollback_strategy_enum.create(bind, checkfirst=True)
    execution_status_enum.create(bind, checkfirst=True)

    if not _has_table(inspector, "action_registry"):
        op.create_table(
            "action_registry",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("action_type", action_type_enum, nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column(
                "required_permissions",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "requires_approval",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column(
                "approval_sla_hours",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("4"),
            ),
            sa.Column("rollback_strategy", rollback_strategy_enum, nullable=False),
            sa.Column(
                "dry_run_supported",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.CheckConstraint("approval_sla_hours >= 1", name="ck_action_registry_approval_sla_positive"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name", name="uq_action_registry_name"),
        )

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "action_executions"):
        op.create_table(
            "action_executions",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("action_name", sa.String(length=120), nullable=False),
            sa.Column("triggered_by", sa.String(length=80), nullable=False),
            sa.Column("status", execution_status_enum, nullable=False, server_default="pending"),
            sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column(
                "payload",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "result",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    if not _has_table(inspector, "action_audit_log"):
        op.create_table(
            "action_audit_log",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("execution_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("step_name", sa.String(length=120), nullable=False),
            sa.Column("actor", sa.String(length=120), nullable=False),
            sa.Column("outcome", sa.String(length=64), nullable=False),
            sa.Column("payload_hash", sa.String(length=64), nullable=False),
            sa.Column(
                "timestamp",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(
                ["execution_id"],
                ["action_executions.id"],
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = sa.inspect(bind)
    if _has_table(inspector, "action_executions") and not _has_index(
        inspector, "action_executions", "ix_action_execution_status_created"
    ):
        op.create_index(
            "ix_action_execution_status_created",
            "action_executions",
            ["status", "created_at"],
            unique=False,
        )

    if _has_table(inspector, "action_audit_log") and not _has_index(
        inspector, "action_audit_log", "ix_action_audit_execution_timestamp"
    ):
        op.create_index(
            "ix_action_audit_execution_timestamp",
            "action_audit_log",
            ["execution_id", "timestamp"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "action_audit_log"):
        if _has_index(inspector, "action_audit_log", "ix_action_audit_execution_timestamp"):
            op.drop_index("ix_action_audit_execution_timestamp", table_name="action_audit_log")
        op.drop_table("action_audit_log")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "action_executions"):
        if _has_index(inspector, "action_executions", "ix_action_execution_status_created"):
            op.drop_index("ix_action_execution_status_created", table_name="action_executions")
        op.drop_table("action_executions")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "action_registry"):
        op.drop_table("action_registry")

    action_type_enum = sa.Enum(name="actiontype")
    rollback_strategy_enum = sa.Enum(name="actionrollbackstrategy")
    execution_status_enum = sa.Enum(name="actionexecutionstatus")

    execution_status_enum.drop(bind, checkfirst=True)
    rollback_strategy_enum.drop(bind, checkfirst=True)
    action_type_enum.drop(bind, checkfirst=True)
