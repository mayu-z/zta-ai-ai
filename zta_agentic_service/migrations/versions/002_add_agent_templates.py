"""add agent template runtime fields and execution logs

Revision ID: 002_add_agent_templates
Revises: 001_baseline_existing_schema
Create Date: 2026-04-16 00:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "002_add_agent_templates"
down_revision = "001_baseline_existing_schema"
branch_labels = None
depends_on = None


def _has_table(inspector: sa.Inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector: sa.Inspector, table_name: str, column_name: str) -> bool:
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _has_index(inspector: sa.Inspector, table_name: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "agent_definitions"):
        if not _has_column(inspector, "agent_definitions", "trigger_config_schema"):
            op.add_column(
                "agent_definitions",
                sa.Column(
                    "trigger_config_schema",
                    postgresql.JSONB(astext_type=sa.Text()),
                    nullable=False,
                    server_default=sa.text("'{}'::jsonb"),
                ),
            )
        if not _has_column(inspector, "agent_definitions", "required_data_scope"):
            op.add_column(
                "agent_definitions",
                sa.Column(
                    "required_data_scope",
                    postgresql.ARRAY(sa.String()),
                    nullable=False,
                    server_default=sa.text("'{}'::varchar[]"),
                ),
            )
        if not _has_column(inspector, "agent_definitions", "output_type"):
            op.add_column(
                "agent_definitions",
                sa.Column("output_type", sa.String(length=32), nullable=False, server_default="read"),
            )
        if not _has_column(inspector, "agent_definitions", "approval_level"):
            op.add_column(
                "agent_definitions",
                sa.Column(
                    "approval_level", sa.String(length=32), nullable=False, server_default="user"
                ),
            )
        if not _has_column(inspector, "agent_definitions", "allowed_personas"):
            op.add_column(
                "agent_definitions",
                sa.Column(
                    "allowed_personas",
                    postgresql.ARRAY(sa.String()),
                    nullable=False,
                    server_default=sa.text("'{}'::varchar[]"),
                ),
            )
        if not _has_column(inspector, "agent_definitions", "handler_class"):
            op.add_column(
                "agent_definitions",
                sa.Column("handler_class", sa.String(length=120), nullable=False, server_default=""),
            )
        if not _has_column(inspector, "agent_definitions", "is_side_effect"):
            op.add_column(
                "agent_definitions",
                sa.Column("is_side_effect", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            )
        if not _has_column(inspector, "agent_definitions", "risk_level"):
            op.add_column(
                "agent_definitions",
                sa.Column("risk_level", sa.String(length=32), nullable=False, server_default="low"),
            )
        if not _has_column(inspector, "agent_definitions", "is_active"):
            op.add_column(
                "agent_definitions",
                sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
            )

    if _has_table(inspector, "tenant_agent_configs"):
        if not _has_column(inspector, "tenant_agent_configs", "config"):
            op.add_column(
                "tenant_agent_configs",
                sa.Column(
                    "config",
                    postgresql.JSONB(astext_type=sa.Text()),
                    nullable=False,
                    server_default=sa.text("'{}'::jsonb"),
                ),
            )
        if not _has_column(inspector, "tenant_agent_configs", "created_by"):
            op.add_column(
                "tenant_agent_configs",
                sa.Column("created_by", sa.String(length=120), nullable=True),
            )
        if not _has_column(inspector, "tenant_agent_configs", "last_triggered_at"):
            op.add_column(
                "tenant_agent_configs",
                sa.Column("last_triggered_at", sa.DateTime(timezone=True), nullable=True),
            )
        if not _has_column(inspector, "tenant_agent_configs", "trigger_count"):
            op.add_column(
                "tenant_agent_configs",
                sa.Column("trigger_count", sa.Integer(), nullable=False, server_default="0"),
            )

        if not _has_index(inspector, "tenant_agent_configs", "ix_agent_instances_config_gin"):
            op.create_index(
                "ix_agent_instances_config_gin",
                "tenant_agent_configs",
                ["config"],
                unique=False,
                postgresql_using="gin",
            )

        if not _has_index(inspector, "tenant_agent_configs", "ix_agent_instances_tenant_template"):
            op.create_index(
                "ix_agent_instances_tenant_template",
                "tenant_agent_configs",
                ["tenant_id", "agent_definition_id"],
                unique=False,
            )

    if not _has_table(inspector, "agent_execution_logs"):
        op.create_table(
            "agent_execution_logs",
            sa.Column(
                "log_id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
            ),
            sa.Column(
                "instance_id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
            ),
            sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("triggered_by", sa.String(length=120), nullable=False),
            sa.Column("user_id", sa.String(length=120), nullable=True),
            sa.Column("action_id", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=64), nullable=False),
            sa.Column("execution_ms", sa.Integer(), nullable=False),
            sa.Column("input_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("output_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("error_detail", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            ),
            sa.ForeignKeyConstraint(
                ["instance_id"],
                ["tenant_agent_configs.id"],
                ondelete="RESTRICT",
            ),
            sa.PrimaryKeyConstraint("log_id"),
        )

    inspector = sa.inspect(bind)
    if _has_table(inspector, "agent_execution_logs") and not _has_index(
        inspector, "agent_execution_logs", "ix_agent_execution_logs_instance_created"
    ):
        op.create_index(
            "ix_agent_execution_logs_instance_created",
            "agent_execution_logs",
            ["instance_id", "created_at"],
            unique=False,
        )

    op.execute("DROP RULE IF EXISTS no_delete_agent_logs ON agent_execution_logs")
    op.execute(
        "CREATE RULE no_delete_agent_logs AS ON DELETE TO agent_execution_logs DO INSTEAD NOTHING"
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "agent_execution_logs"):
        op.execute("DROP RULE IF EXISTS no_delete_agent_logs ON agent_execution_logs")

    if _has_table(inspector, "tenant_agent_configs"):
        if _has_index(inspector, "tenant_agent_configs", "ix_agent_instances_config_gin"):
            op.drop_index("ix_agent_instances_config_gin", table_name="tenant_agent_configs")
        if _has_index(inspector, "tenant_agent_configs", "ix_agent_instances_tenant_template"):
            op.drop_index("ix_agent_instances_tenant_template", table_name="tenant_agent_configs")

    if _has_table(inspector, "agent_execution_logs"):
        if _has_index(inspector, "agent_execution_logs", "ix_agent_execution_logs_instance_created"):
            op.drop_index("ix_agent_execution_logs_instance_created", table_name="agent_execution_logs")
        op.drop_table("agent_execution_logs")

    inspector = sa.inspect(bind)
    if _has_table(inspector, "tenant_agent_configs"):
        if _has_column(inspector, "tenant_agent_configs", "trigger_count"):
            op.drop_column("tenant_agent_configs", "trigger_count")
        if _has_column(inspector, "tenant_agent_configs", "last_triggered_at"):
            op.drop_column("tenant_agent_configs", "last_triggered_at")
        if _has_column(inspector, "tenant_agent_configs", "created_by"):
            op.drop_column("tenant_agent_configs", "created_by")
        if _has_column(inspector, "tenant_agent_configs", "config"):
            op.drop_column("tenant_agent_configs", "config")

    if _has_table(inspector, "agent_definitions"):
        if _has_column(inspector, "agent_definitions", "is_active"):
            op.drop_column("agent_definitions", "is_active")
        if _has_column(inspector, "agent_definitions", "risk_level"):
            op.drop_column("agent_definitions", "risk_level")
        if _has_column(inspector, "agent_definitions", "is_side_effect"):
            op.drop_column("agent_definitions", "is_side_effect")
        if _has_column(inspector, "agent_definitions", "handler_class"):
            op.drop_column("agent_definitions", "handler_class")
        if _has_column(inspector, "agent_definitions", "allowed_personas"):
            op.drop_column("agent_definitions", "allowed_personas")
        if _has_column(inspector, "agent_definitions", "approval_level"):
            op.drop_column("agent_definitions", "approval_level")
        if _has_column(inspector, "agent_definitions", "output_type"):
            op.drop_column("agent_definitions", "output_type")
        if _has_column(inspector, "agent_definitions", "required_data_scope"):
            op.drop_column("agent_definitions", "required_data_scope")
        if _has_column(inspector, "agent_definitions", "trigger_config_schema"):
            op.drop_column("agent_definitions", "trigger_config_schema")
