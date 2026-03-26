from __future__ import annotations

from app.connectors.mock_claims import mock_claims_connector
from app.schemas.pipeline import CompiledQueryPlan


class ConnectorRegistry:
    def get(self, plan: CompiledQueryPlan):
        # MVP runtime executes against claim store via mock connector.
        # Real adapters are available as structured stubs for production wiring.
        if plan.source_type == "mock_claims":
            return mock_claims_connector
        return mock_claims_connector


connector_registry = ConnectorRegistry()
