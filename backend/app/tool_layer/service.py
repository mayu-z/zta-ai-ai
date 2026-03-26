from __future__ import annotations

from sqlalchemy.orm import Session

from app.connectors.registry import connector_registry
from app.schemas.pipeline import CompiledQueryPlan


class ToolLayerService:
    def execute(self, db: Session, plan: CompiledQueryPlan) -> dict[str, object]:
        connector = connector_registry.get(plan)
        connector.connect()
        return connector.execute_query(db, plan)


tool_layer_service = ToolLayerService()
