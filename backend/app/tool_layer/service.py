from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.source_types import is_local_store_source_type
from app.connectors.registry import connector_registry
from app.core.exceptions import ValidationError
from app.db.models import AuditLog, DataSource
from app.db.models import DataSourceStatus
from app.schemas.pipeline import CompiledQueryPlan


class ToolLayerService:
    def execute(self, db: Session, plan: CompiledQueryPlan) -> dict[str, object]:
        # Handle admin queries directly without connector execution.
        if plan.filters.get("entity_type") == "admin_data_sources":
            return self._get_data_sources(db, plan)
        if plan.filters.get("entity_type") == "admin_audit_log":
            return self._get_audit_log(db, plan)

        bound_source: DataSource | None = None
        if plan.data_source_id:
            bound_source = db.scalar(
                select(DataSource).where(
                    DataSource.id == plan.data_source_id,
                    DataSource.tenant_id == plan.tenant_id,
                )
            )
            if not bound_source:
                raise ValidationError(
                    message="Compiled plan references an unknown data source",
                    code="PLAN_SOURCE_NOT_FOUND",
                )
            if bound_source.status != DataSourceStatus.connected:
                raise ValidationError(
                    message="Compiled plan references a disconnected data source",
                    code="PLAN_SOURCE_NOT_CONNECTED",
                )
            if bound_source.source_type.value != plan.source_type:
                raise ValidationError(
                    message="Compiled plan source type does not match bound data source",
                    code="PLAN_SOURCE_MISMATCH",
                )
        elif not is_local_store_source_type(plan.source_type):
            raise ValidationError(
                message="Non-local source routing requires a bound data_source_id",
                code="PLAN_SOURCE_BINDING_INCOMPLETE",
            )

        connector = connector_registry.get(plan, bound_source)
        connector.connect()
        return connector.execute_query(db, plan)

    def _get_data_sources(
        self, db: Session, plan: CompiledQueryPlan
    ) -> dict[str, object]:
        tenant_id = plan.filters.get("tenant_id")
        rows = db.scalars(
            select(DataSource).where(DataSource.tenant_id == tenant_id)
        ).all()
        sources = [
            {
                "id": row.id,
                "name": row.name,
                "source_type": row.source_type.value,
                "status": row.status.value,
                "last_sync_at": str(row.last_sync_at) if row.last_sync_at else None,
            }
            for row in rows
        ]
        return {"sources": sources, "count": len(sources)}

    def _get_audit_log(self, db: Session, plan: CompiledQueryPlan) -> dict[str, object]:
        tenant_id = plan.filters.get("tenant_id")
        rows = db.scalars(
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant_id)
            .order_by(AuditLog.created_at.desc())
            .limit(10)
        ).all()
        entries = [
            {
                "id": row.id,
                "user_id": row.user_id,
                "query_text": (
                    row.query_text[:50] + "..."
                    if row.query_text and len(row.query_text) > 50
                    else row.query_text
                ),
                "was_blocked": row.was_blocked,
                "created_at": str(row.created_at) if row.created_at else None,
            }
            for row in rows
        ]
        return {"entries": entries, "count": len(entries)}


tool_layer_service = ToolLayerService()
