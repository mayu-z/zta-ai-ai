from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agentic.connectors.base import ConnectorError
from app.agentic.connectors.registry import ConnectorPool


@pytest.mark.asyncio
async def test_mock_source_type_blocked_in_production(monkeypatch) -> None:
    pool = ConnectorPool()
    tenant_id = uuid4()

    monkeypatch.setattr(
        "app.agentic.connectors.registry.get_settings",
        lambda: SimpleNamespace(environment="production"),
    )

    with pytest.raises(ConnectorError):
        await pool.get(
            tenant_id=tenant_id,
            source_type="mock",
            source_id="mock-source",
            config={},
        )


@pytest.mark.asyncio
async def test_unknown_source_type_is_rejected() -> None:
    pool = ConnectorPool()
    tenant_id = uuid4()

    with pytest.raises(ConnectorError):
        await pool.get(
            tenant_id=tenant_id,
            source_type="mssql",
            source_id="sql-1",
            config={},
        )
