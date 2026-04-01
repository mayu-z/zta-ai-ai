from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.registry import connector_registry
from app.db.models import AuditLog, DataSource
from app.schemas.pipeline import CompiledQueryPlan


class ToolLayerService:
    def execute(self, db: Session, plan: CompiledQueryPlan) -> dict[str, object]:
        # Handle admin queries directly without claims
        if plan.filters.get("entity_type") == "admin_data_sources":
            return self._get_data_sources(db, plan)
        if plan.filters.get("entity_type") == "admin_audit_log":
            return self._get_audit_log(db, plan)

        connector = connector_registry.get(plan)
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
